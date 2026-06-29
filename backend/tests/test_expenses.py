import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal


def _calc_work_minutes(clock_in: datetime, clock_out: datetime, break_minutes: int) -> tuple[int, int]:
    """Replicate the attendance work/overtime calculation."""
    total = int((clock_out - clock_in).total_seconds() / 60)
    work = max(total - break_minutes, 0)
    overtime = max(work - 480, 0)
    return work, overtime


def _calc_expense_total(items: list[Decimal]) -> Decimal:
    """Replicate the expense total calculation."""
    return sum(items)


class TestAttendanceWorkCalculation:
    def test_standard_8h_no_overtime(self):
        clock_in = datetime(2026, 6, 1, 9, 0)
        clock_out = datetime(2026, 6, 1, 18, 0)
        work, overtime = _calc_work_minutes(clock_in, clock_out, 60)
        assert work == 480
        assert overtime == 0

    def test_overtime(self):
        clock_in = datetime(2026, 6, 1, 9, 0)
        clock_out = datetime(2026, 6, 1, 21, 0)
        work, overtime = _calc_work_minutes(clock_in, clock_out, 60)
        assert work == 660
        assert overtime == 180

    def test_short_day(self):
        clock_in = datetime(2026, 6, 1, 9, 0)
        clock_out = datetime(2026, 6, 1, 13, 0)
        work, overtime = _calc_work_minutes(clock_in, clock_out, 60)
        assert work == 180
        assert overtime == 0

    def test_no_break(self):
        clock_in = datetime(2026, 6, 1, 9, 0)
        clock_out = datetime(2026, 6, 1, 17, 0)
        work, overtime = _calc_work_minutes(clock_in, clock_out, 0)
        assert work == 480
        assert overtime == 0

    def test_long_break_clamped_to_zero(self):
        clock_in = datetime(2026, 6, 1, 9, 0)
        clock_out = datetime(2026, 6, 1, 10, 0)
        work, overtime = _calc_work_minutes(clock_in, clock_out, 120)
        assert work == 0
        assert overtime == 0


class TestExpenseTotalCalculation:
    def test_single_item(self):
        total = _calc_expense_total([Decimal("1500")])
        assert total == Decimal("1500")

    def test_multiple_items(self):
        total = _calc_expense_total([Decimal("1500"), Decimal("3000"), Decimal("850")])
        assert total == Decimal("5350")

    def test_zero_amount(self):
        total = _calc_expense_total([Decimal("0"), Decimal("1000")])
        assert total == Decimal("1000")

    def test_empty_items(self):
        total = _calc_expense_total([])
        assert total == Decimal("0")


class TestExpenseCategoryValidation:
    VALID_CATEGORIES = {"transport", "meal", "accommodation", "supplies", "entertainment", "other"}

    def test_all_valid_categories(self):
        for cat in ["transport", "meal", "accommodation", "supplies", "entertainment", "other"]:
            assert cat in self.VALID_CATEGORIES

    def test_invalid_category(self):
        assert "food" not in self.VALID_CATEGORIES
        assert "" not in self.VALID_CATEGORIES
        assert "TRANSPORT" not in self.VALID_CATEGORIES


class TestExpenseStatusTransitions:
    VALID_TRANSITIONS = {
        "submitted": {"approved", "rejected"},
        "approved": {"paid"},
        "rejected": set(),
        "paid": set(),
    }

    def test_submitted_to_approved(self):
        assert "approved" in self.VALID_TRANSITIONS["submitted"]

    def test_submitted_to_rejected(self):
        assert "rejected" in self.VALID_TRANSITIONS["submitted"]

    def test_approved_to_paid(self):
        assert "paid" in self.VALID_TRANSITIONS["approved"]

    def test_approved_to_rejected_not_allowed(self):
        assert "rejected" not in self.VALID_TRANSITIONS["approved"]

    def test_paid_no_transitions(self):
        assert len(self.VALID_TRANSITIONS["paid"]) == 0

    def test_rejected_no_transitions(self):
        assert len(self.VALID_TRANSITIONS["rejected"]) == 0

    def test_submitted_to_paid_not_allowed(self):
        assert "paid" not in self.VALID_TRANSITIONS["submitted"]
