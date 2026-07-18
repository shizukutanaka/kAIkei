from decimal import ROUND_DOWN, Decimal

import pytest

from app.services.entertainment_expense import EntertainmentExpenseService


class TestEntertainmentExpenseService:
    def test_small_corporation_flat_wins(self):
        result = EntertainmentExpenseService.compute(
            Decimal("10000000"),
            Decimal("4000000"),
            Decimal("50000000"),
        )
        assert result.deductible_limit == Decimal("8000000")
        assert result.deductible_amount == Decimal("8000000")
        assert result.non_deductible_amount == Decimal("2000000")
        assert result.basis == "flat_8m"

    def test_small_corporation_dining_50pct_wins(self):
        result = EntertainmentExpenseService.compute(
            Decimal("25000000"),
            Decimal("20000000"),
            Decimal("50000000"),
        )
        assert result.deductible_limit == Decimal("10000000")
        assert result.deductible_amount == Decimal("10000000")
        assert result.non_deductible_amount == Decimal("15000000")
        assert result.basis == "dining_50pct"

    def test_large_corporation(self):
        result = EntertainmentExpenseService.compute(
            Decimal("12000000"),
            Decimal("10000000"),
            Decimal("200000000"),
        )
        assert result.deductible_limit == Decimal("5000000")
        assert result.deductible_amount == Decimal("5000000")
        assert result.non_deductible_amount == Decimal("7000000")
        assert result.basis == "dining_50pct"

    def test_capital_over_10bn_gets_no_deduction(self):
        # 令和2年度改正: 資本金100億円超は接待飲食費50%特例も不可（損金算入限度額0）。
        result = EntertainmentExpenseService.compute(
            Decimal("12000000"),
            Decimal("10000000"),
            Decimal("10000000001"),  # 100億円超
        )
        assert result.deductible_limit == Decimal("0")
        assert result.deductible_amount == Decimal("0")
        assert result.non_deductible_amount == Decimal("12000000")
        assert result.basis == "no_deduction_over_10bn"

    def test_capital_exactly_10bn_still_gets_dining_deduction(self):
        # 100億円ちょうどは「超」に当たらず50%特例が適用される。
        result = EntertainmentExpenseService.compute(
            Decimal("12000000"),
            Decimal("10000000"),
            Decimal("10000000000"),  # 100億円ちょうど
        )
        assert result.deductible_limit == Decimal("5000000")
        assert result.basis == "dining_50pct"

    def test_threshold_capital_inclusive_small(self):
        result = EntertainmentExpenseService.compute(
            Decimal("9000000"),
            Decimal("1000000"),
            Decimal("100000000"),
        )
        assert result.basis == "flat_8m"

    def test_fully_within_limit(self):
        result = EntertainmentExpenseService.compute(
            Decimal("3000000"),
            Decimal("1000000"),
            Decimal("50000000"),
        )
        assert result.deductible_amount == Decimal("3000000")
        assert result.non_deductible_amount == Decimal("0")

    def test_flooring_case(self):
        total_entertainment = Decimal("1234567")
        dining_expense = Decimal("1234567")
        result = EntertainmentExpenseService.compute(total_entertainment, dining_expense, Decimal("200000000"))
        expected_limit = (dining_expense * Decimal("0.50")).quantize(Decimal("1"), rounding=ROUND_DOWN)
        assert result.deductible_limit == expected_limit
        assert result.basis == "dining_50pct"

    def test_dining_exceeds_total_raises(self):
        with pytest.raises(ValueError):
            EntertainmentExpenseService.compute(Decimal("1000"), Decimal("1001"), Decimal("50000000"))

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            EntertainmentExpenseService.compute(Decimal("-1"), Decimal("0"), Decimal("0"))
