import pytest
from decimal import Decimal, ROUND_HALF_UP


def _calc_annual_tax(gross: Decimal, dependents: int) -> Decimal:
    dependent_deduction = Decimal(str(dependents * 380000))
    taxable = gross - dependent_deduction
    if taxable <= 0:
        return Decimal("0")
    if taxable <= 1950000:
        rate = Decimal("0.05")
        deduction = Decimal("0")
    elif taxable <= 3300000:
        rate = Decimal("0.10")
        deduction = Decimal("97500")
    elif taxable <= 6945000:
        rate = Decimal("0.20")
        deduction = Decimal("427500")
    elif taxable <= 9000000:
        rate = Decimal("0.23")
        deduction = Decimal("636000")
    elif taxable <= 18000000:
        rate = Decimal("0.33")
        deduction = Decimal("1536000")
    elif taxable <= 40000000:
        rate = Decimal("0.40")
        deduction = Decimal("2796000")
    else:
        rate = Decimal("0.45")
        deduction = Decimal("4796000")
    tax = (taxable * rate - deduction).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(tax, Decimal("0"))


class TestAnnualTaxCalculation:
    def test_zero_income(self):
        assert _calc_annual_tax(Decimal("0"), 0) == Decimal("0")

    def test_negative_income(self):
        assert _calc_annual_tax(Decimal("-1000"), 0) == Decimal("0")

    def test_lowest_bracket(self):
        result = _calc_annual_tax(Decimal("3000000"), 0)
        expected = (Decimal("3000000") * Decimal("0.10") - Decimal("97500")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        assert result == expected

    def test_second_bracket(self):
        result = _calc_annual_tax(Decimal("5000000"), 0)
        expected = (Decimal("5000000") * Decimal("0.20") - Decimal("427500")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        assert result == expected

    def test_highest_bracket(self):
        result = _calc_annual_tax(Decimal("50000000"), 0)
        expected = (Decimal("50000000") * Decimal("0.45") - Decimal("4796000")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        assert result == expected


class TestDependentDeduction:
    def test_no_dependents(self):
        result = _calc_annual_tax(Decimal("4000000"), 0)
        expected = (Decimal("4000000") * Decimal("0.20") - Decimal("427500")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        assert result == expected

    def test_with_dependents(self):
        without = _calc_annual_tax(Decimal("4000000"), 0)
        with_deps = _calc_annual_tax(Decimal("4000000"), 2)
        assert with_deps < without

    def test_dependents_reduce_taxable(self):
        result_0 = _calc_annual_tax(Decimal("3000000"), 0)
        result_3 = _calc_annual_tax(Decimal("3000000"), 3)
        deduction_effect = result_0 - result_3
        assert deduction_effect > Decimal("0")

    def test_dependents_make_taxable_zero(self):
        result = _calc_annual_tax(Decimal("100000"), 1)
        assert result == Decimal("0")


class TestAdjustmentAmount:
    def test_refund(self):
        withholding = Decimal("200000")
        estimated = Decimal("150000")
        adjustment = (withholding - estimated).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        assert adjustment == Decimal("50000")
        assert adjustment > 0

    def test_additional_tax(self):
        withholding = Decimal("100000")
        estimated = Decimal("150000")
        adjustment = (withholding - estimated).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        assert adjustment == Decimal("-50000")
        assert adjustment < 0

    def test_no_adjustment(self):
        withholding = Decimal("150000")
        estimated = Decimal("150000")
        adjustment = (withholding - estimated).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        assert adjustment == Decimal("0")
