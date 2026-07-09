from datetime import date
from decimal import Decimal

import pytest

from app.services.audit_detection import (
    JournalSnapshot,
    detect_backdated,
    detect_duplicate,
    detect_high_amount,
    detect_round_amount,
    detect_sod_conflict,
    detect_weekend_entry,
    highest_risk,
    run_rules,
)


def _snap(**kw):
    base = dict(
        journal_header_id="jh-1",
        transaction_date=date(2026, 4, 15),  # 水曜日
        created_on=date(2026, 4, 15),
        total_amount=Decimal("50000"),
        created_by="u1",
        approved_by="u2",
        summary="",
        counterparty="",
    )
    base.update(kw)
    return JournalSnapshot(**base)


class TestHighAmount:
    def test_flags_at_or_above_threshold(self):
        assert detect_high_amount(_snap(total_amount=Decimal("1000000"))) is not None

    def test_ignores_below_threshold(self):
        assert detect_high_amount(_snap(total_amount=Decimal("999999"))) is None

    def test_risk_is_high(self):
        f = detect_high_amount(_snap(total_amount=Decimal("2000000")))
        assert f.risk_level == "high"


class TestRoundAmount:
    def test_flags_multiple_of_modulus(self):
        assert detect_round_amount(_snap(total_amount=Decimal("300000"))) is not None

    def test_ignores_non_round(self):
        assert detect_round_amount(_snap(total_amount=Decimal("312500"))) is None

    def test_ignores_small_round(self):
        assert detect_round_amount(_snap(total_amount=Decimal("50000"))) is None


class TestWeekendEntry:
    def test_saturday_flagged(self):
        assert detect_weekend_entry(_snap(transaction_date=date(2026, 4, 18))) is not None  # 土

    def test_sunday_flagged(self):
        assert detect_weekend_entry(_snap(transaction_date=date(2026, 4, 19))) is not None  # 日

    def test_weekday_not_flagged(self):
        assert detect_weekend_entry(_snap(transaction_date=date(2026, 4, 15))) is None  # 水


class TestBackdated:
    def test_flags_beyond_lag(self):
        f = detect_backdated(
            _snap(transaction_date=date(2026, 1, 1), created_on=date(2026, 4, 15)),
            max_lag_days=30,
        )
        assert f is not None and f.details["lag_days"] > 30

    def test_within_lag_ok(self):
        assert detect_backdated(
            _snap(transaction_date=date(2026, 4, 1), created_on=date(2026, 4, 15)),
            max_lag_days=30,
        ) is None

    def test_future_transaction_not_backdated(self):
        assert detect_backdated(
            _snap(transaction_date=date(2026, 4, 20), created_on=date(2026, 4, 15))
        ) is None


class TestSodConflict:
    def test_same_creator_and_approver_flagged(self):
        assert detect_sod_conflict(_snap(created_by="u1", approved_by="u1")) is not None

    def test_different_ok(self):
        assert detect_sod_conflict(_snap(created_by="u1", approved_by="u2")) is None

    def test_no_approver_ok(self):
        assert detect_sod_conflict(_snap(created_by="u1", approved_by=None)) is None


class TestDuplicate:
    def test_detects_same_amount_date_counterparty(self):
        a = _snap(journal_header_id="a", total_amount=Decimal("10000"), counterparty="カイケイ")
        b = _snap(journal_header_id="b", total_amount=Decimal("10000"), counterparty="カイケイ")
        assert detect_duplicate(a, [a, b]) is not None

    def test_ignores_self(self):
        a = _snap(journal_header_id="a")
        assert detect_duplicate(a, [a]) is None

    def test_different_counterparty_not_duplicate(self):
        a = _snap(journal_header_id="a", counterparty="X")
        b = _snap(journal_header_id="b", counterparty="Y")
        assert detect_duplicate(a, [b]) is None


class TestRunRulesAndRisk:
    def test_clean_journal_no_findings(self):
        assert run_rules(_snap(created_by="u1", approved_by="u2")) == []

    def test_multiple_findings(self):
        # 高額 + 丸め + 休日 + SoD
        snap = _snap(
            total_amount=Decimal("2000000"),
            transaction_date=date(2026, 4, 18),  # 土
            created_by="u1",
            approved_by="u1",
        )
        cats = {f.category for f in run_rules(snap)}
        assert {"high_amount", "round_amount", "weekend_entry", "sod_conflict"} <= cats

    def test_highest_risk(self):
        snap = _snap(total_amount=Decimal("2000000"), created_by="u1", approved_by="u1")
        assert highest_risk(run_rules(snap)) == "high"

    def test_highest_risk_none_when_empty(self):
        assert highest_risk([]) is None
