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
