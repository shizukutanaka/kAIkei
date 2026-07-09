from decimal import Decimal

import pytest

from app.services.ai_inference_log import (
    AUTO_COMMIT_THRESHOLD,
    compute_accuracy_stats,
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
