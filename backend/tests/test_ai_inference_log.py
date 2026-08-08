from decimal import Decimal

import pytest

from app.services.ai_inference_log import (
    AUTO_COMMIT_THRESHOLD,
    compute_accuracy_stats,
    compute_calibration_stats,
    compute_correction_diff,
    confidence_band,
    should_auto_commit,
)


class TestConfidenceBand:
    def test_high(self):
        assert confidence_band(Decimal("0.95")) == "high"
        assert confidence_band(Decimal("0.90")) == "high"

    def test_medium(self):
        assert confidence_band(Decimal("0.75")) == "medium"
        assert confidence_band(Decimal("0.70")) == "medium"

    def test_low(self):
        assert confidence_band(Decimal("0.5")) == "low"


class TestShouldAutoCommit:
    def test_at_threshold_commits(self):
        assert should_auto_commit(AUTO_COMMIT_THRESHOLD) is True

    def test_above_threshold(self):
        assert should_auto_commit(Decimal("0.99")) is True

    def test_below_threshold(self):
        assert should_auto_commit(Decimal("0.90")) is False


class TestCorrectionDiff:
    def test_no_changes(self):
        s = {"account_code": "1110", "amount": 1000}
        assert compute_correction_diff(s, dict(s)) == {}

    def test_changed_field(self):
        s = {"account_code": "1110", "amount": 1000}
        f = {"account_code": "5210", "amount": 1000}
        diff = compute_correction_diff(s, f)
        assert diff == {"account_code": {"from": "1110", "to": "5210"}}

    def test_added_and_removed_keys(self):
        s = {"a": 1}
        f = {"b": 2}
        diff = compute_correction_diff(s, f)
        assert diff["a"] == {"from": 1, "to": None}
        assert diff["b"] == {"from": None, "to": 2}


class TestAccuracyStats:
    def test_empty(self):
        stats = compute_accuracy_stats([])
        assert stats["total"] == 0
        assert stats["acceptance_rate"] == 0.0
        assert stats["correction_rate"] == 0.0

    def test_acceptance_and_correction_rates(self):
        logs = [
            {"applied": True, "correction_diff": None, "confidence": Decimal("0.9")},
            {"applied": True, "correction_diff": {"x": 1}, "confidence": Decimal("0.8")},
            {"applied": False, "correction_diff": None, "confidence": Decimal("0.6")},
            {"applied": False, "correction_diff": None, "confidence": Decimal("0.5")},
        ]
        stats = compute_accuracy_stats(logs)
        assert stats["total"] == 4
        assert stats["applied"] == 2
        assert stats["acceptance_rate"] == 0.5
        assert stats["corrected"] == 1
        assert stats["correction_rate"] == 0.5
        assert stats["avg_confidence"] == pytest.approx(0.7, abs=0.01)

    def test_correction_rate_zero_when_none_applied(self):
        logs = [{"applied": False, "correction_diff": None, "confidence": Decimal("0.5")}]
        assert compute_accuracy_stats(logs)["correction_rate"] == 0.0

class TestCalibrationStats:
    def _log(self, conf, applied=True, corrected=False):
        return {
            "applied": applied,
            "correction_diff": {"x": 1} if corrected else None,
            "confidence": Decimal(conf),
        }

    def test_empty(self):
        stats = compute_calibration_stats([])
        assert stats["applied_total"] == 0
        assert stats["ece"] == 0.0
        assert all(b["count"] == 0 for b in stats["bands"])

    def test_well_calibrated_high_band(self):
        # 信頼度0.95で10件中9件が無修正 → gap ≈ 0.05
        logs = [self._log("0.95") for _ in range(9)] + [self._log("0.95", corrected=True)]
        stats = compute_calibration_stats(logs)
        high = next(b for b in stats["bands"] if b["band"] == "high")
        assert high["count"] == 10
        assert high["observed_accuracy"] == 0.9
        assert high["gap"] == pytest.approx(0.05, abs=0.001)
        assert stats["ece"] == pytest.approx(0.05, abs=0.001)

    def test_overconfident_flagged_by_large_gap(self):
        # 信頼度0.95なのに半数が修正される → gap ≈ 0.45（過信）
        logs = [self._log("0.95") for _ in range(5)] + [self._log("0.95", corrected=True) for _ in range(5)]
        stats = compute_calibration_stats(logs)
        high = next(b for b in stats["bands"] if b["band"] == "high")
        assert high["gap"] == pytest.approx(0.45, abs=0.001)

    def test_unapplied_logs_excluded(self):
        logs = [self._log("0.95", applied=False) for _ in range(5)]
        stats = compute_calibration_stats(logs)
        assert stats["applied_total"] == 0

    def test_band_partitioning(self):
        logs = [self._log("0.5"), self._log("0.8"), self._log("0.95")]
        stats = compute_calibration_stats(logs)
        counts = {b["band"]: b["count"] for b in stats["bands"]}
        assert counts == {"low": 1, "medium": 1, "high": 1}


class TestFineGrainedCalibration:
    """粗いバンド集計では隠れる較正ずれを検出できること。"""

    def _logs(self, spec: list[tuple[str, int, int]]) -> list[dict]:
        """spec = [(confidence, 件数, 正答数)] からログ列を作る。"""
        out: list[dict] = []
        for conf, n, correct in spec:
            for i in range(n):
                out.append({
                    "applied": True,
                    "confidence": Decimal(conf),
                    "correction_diff": None if i < correct else {"account": {"from": "a", "to": "b"}},
                })
        return out

    def test_wide_band_masks_miscalibration_but_fine_bins_detect_it(self):
        """回帰: high帯[0.90,1.01)内で逆方向の誤差が相殺されるケース。

        信頼度0.91→実正答99%(自信不足)、0.99→実正答91%(自信過剰)。
        平均は0.95/0.95で一致するためバンド単位のECEは0になるが、
        実際には自動コミット領域(>=0.95)が9%の誤りを含む。
        """
        logs = self._logs([("0.91", 100, 99), ("0.99", 100, 91)])
        stats = compute_calibration_stats(logs)

        assert stats["ece"] == pytest.approx(0.0, abs=0.001)      # 粗い指標は見逃す
        assert stats["ece_binned"] > 0.05                          # 等幅ビンは検出
        assert stats["ece_adaptive"] > 0.05                        # 等件数ビンも検出

    def test_auto_commit_accuracy_is_measured_directly(self):
        logs = self._logs([("0.91", 100, 99), ("0.99", 100, 91)])
        ac = compute_calibration_stats(logs)["auto_commit"]
        assert ac["threshold"] == 0.95
        assert ac["count"] == 100                    # 0.99の100件のみが対象
        assert ac["observed_accuracy"] == pytest.approx(0.91, abs=0.001)
        assert ac["signed_gap"] > 0                  # 自信過剰
        assert ac["overconfident"] is True           # 実正答率が閾値未満 → 危険

    def test_well_calibrated_auto_commit_not_flagged(self):
        logs = self._logs([("0.96", 100, 97)])
        ac = compute_calibration_stats(logs)["auto_commit"]
        assert ac["observed_accuracy"] == pytest.approx(0.97, abs=0.001)
        assert ac["overconfident"] is False          # 実正答率97% >= 閾値95%

    def test_signed_gap_direction(self):
        over = compute_calibration_stats(self._logs([("0.95", 100, 50)]))
        under = compute_calibration_stats(self._logs([("0.50", 100, 100)]))
        assert over["signed_gap"] > 0     # 自信過剰（危険側）
        assert under["signed_gap"] < 0    # 自信不足（安全側）

    def test_no_auto_commit_candidates(self):
        ac = compute_calibration_stats(self._logs([("0.80", 10, 8)]))["auto_commit"]
        assert ac["count"] == 0
        assert ac["observed_accuracy"] is None
        assert ac["overconfident"] is False

    def test_empty_logs_have_zero_metrics(self):
        stats = compute_calibration_stats([])
        assert stats["ece_binned"] == 0.0
        assert stats["ece_adaptive"] == 0.0
        assert stats["signed_gap"] == 0.0
        assert stats["auto_commit"]["count"] == 0
