import pytest
from decimal import Decimal, ROUND_HALF_UP


def _calc_income_tax(gross: Decimal) -> Decimal:
    if gross <= 0:
        return Decimal("0")
    return (gross * Decimal("0.05")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _calc_social_insurance(gross: Decimal) -> Decimal:
    if gross <= 0:
        return Decimal("0")
    return (gross * Decimal("0.15")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class TestPayrollTaxCalculation:
    def test_income_tax_zero(self):
        assert _calc_income_tax(Decimal("0")) == Decimal("0")

    def test_income_tax_negative(self):
        assert _calc_income_tax(Decimal("-1000")) == Decimal("0")

    def test_income_tax_basic(self):
        result = _calc_income_tax(Decimal("300000"))
        assert result == Decimal("15000")

    def test_income_tax_rounding(self):
        result = _calc_income_tax(Decimal("333333"))
        assert result == Decimal("16667")

    def test_social_insurance_zero(self):
        assert _calc_social_insurance(Decimal("0")) == Decimal("0")

    def test_social_insurance_negative(self):
        assert _calc_social_insurance(Decimal("-1000")) == Decimal("0")

    def test_social_insurance_basic(self):
        result = _calc_social_insurance(Decimal("300000"))
        assert result == Decimal("45000")

    def test_social_insurance_rounding(self):
        result = _calc_social_insurance(Decimal("333333"))
        assert result == Decimal("50000")


class TestPayrollCalculateLogic:
    def test_overtime_pay_calculation(self):
        """残業代 = 時給 × 残業時間 × 1.25"""
        hourly_rate = Decimal("1500")
        overtime_hours = Decimal("10")
        overtime_pay = (hourly_rate * overtime_hours * Decimal("1.25")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        assert overtime_pay == Decimal("18750")

    def test_total_gross_calculation(self):
        base_salary = Decimal("250000")
        overtime_pay = Decimal("18750")
        total_gross = base_salary + overtime_pay
        assert total_gross == Decimal("268750")

    def test_net_pay_calculation(self):
        total_gross = Decimal("268750")
        income_tax = _calc_income_tax(total_gross)
        social_ins = _calc_social_insurance(total_gross)
        total_deductions = income_tax + social_ins
        net_pay = total_gross - total_deductions
        assert net_pay == Decimal("268750") - income_tax - social_ins
        assert net_pay > Decimal("0")

    def test_zero_overtime(self):
        hourly_rate = Decimal("1500")
        overtime_hours = Decimal("0")
        overtime_pay = (hourly_rate * overtime_hours * Decimal("1.25")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        assert overtime_pay == Decimal("0")

    def test_part_time_overtime(self):
        """パートタイムの残業代計算"""
        hourly_rate = Decimal("1200")
        overtime_hours = Decimal("5.5")
        overtime_pay = (hourly_rate * overtime_hours * Decimal("1.25")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        assert overtime_pay == Decimal("8250")
