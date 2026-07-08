from decimal import ROUND_DOWN, Decimal

import pytest

from app.services.salary_deduction import SalaryIncomeDeductionService


class TestSalaryIncomeDeductionService:
    def test_boundary_values(self):
        assert SalaryIncomeDeductionService.compute(Decimal("1625000")) == Decimal("550000")
        assert SalaryIncomeDeductionService.compute(Decimal("1800000")) == Decimal("620000")
        assert SalaryIncomeDeductionService.compute(Decimal("3600000")) == Decimal("1160000")
        assert SalaryIncomeDeductionService.compute(Decimal("6600000")) == Decimal("1760000")
        assert SalaryIncomeDeductionService.compute(Decimal("8500000")) == Decimal("1950000")
        assert SalaryIncomeDeductionService.compute(Decimal("10000000")) == Decimal("1950000")

    def test_low_value_uses_fixed_floor(self):
        assert SalaryIncomeDeductionService.compute(Decimal("1000000")) == Decimal("550000")

    def test_mid_bracket_value(self):
        gross_salary = Decimal("5000000")
        expected = (gross_salary * Decimal("0.20") + Decimal("440000")).quantize(Decimal("1"), rounding=ROUND_DOWN)

        assert SalaryIncomeDeductionService.compute(gross_salary) == expected
        assert expected == Decimal("1440000")

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            SalaryIncomeDeductionService.compute(Decimal("-1"))
