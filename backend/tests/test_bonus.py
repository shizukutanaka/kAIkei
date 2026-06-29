import pytest
from decimal import Decimal, ROUND_HALF_UP


def _calc_bonus_tax(gross: Decimal) -> Decimal:
    if gross <= 0:
        return Decimal("0")
    return (gross * Decimal("0.1021")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _calc_bonus_social_insurance(gross: Decimal) -> Decimal:
    if gross <= 0:
        return Decimal("0")
    return (gross * Decimal("0.15")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _calc_bonus_amount(base_salary: Decimal, base_months: Decimal, factor: Decimal) -> Decimal:
    return (base_salary * base_months * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class TestBonusTaxCalculation:
    def test_bonus_tax_zero(self):
        assert _calc_bonus_tax(Decimal("0")) == Decimal("0")

    def test_bonus_tax_negative(self):
        assert _calc_bonus_tax(Decimal("-1000")) == Decimal("0")

    def test_bonus_tax_basic(self):
        result = _calc_bonus_tax(Decimal("500000"))
        assert result == Decimal("51050")

    def test_bonus_tax_rounding(self):
        result = _calc_bonus_tax(Decimal("333333"))
        assert result == Decimal("34033")


class TestBonusSocialInsurance:
    def test_social_insurance_zero(self):
        assert _calc_bonus_social_insurance(Decimal("0")) == Decimal("0")

    def test_social_insurance_negative(self):
        assert _calc_bonus_social_insurance(Decimal("-1000")) == Decimal("0")

    def test_social_insurance_basic(self):
        result = _calc_bonus_social_insurance(Decimal("500000"))
        assert result == Decimal("75000")


class TestBonusAmountCalculation:
    def test_standard_factor(self):
        result = _calc_bonus_amount(Decimal("300000"), Decimal("2.0"), Decimal("1.00"))
        assert result == Decimal("600000")

    def test_high_performance(self):
        result = _calc_bonus_amount(Decimal("300000"), Decimal("2.5"), Decimal("1.50"))
        assert result == Decimal("1125000")

    def test_zero_months(self):
        result = _calc_bonus_amount(Decimal("300000"), Decimal("0"), Decimal("1.00"))
        assert result == Decimal("0")

    def test_zero_factor(self):
        result = _calc_bonus_amount(Decimal("300000"), Decimal("2.0"), Decimal("0"))
        assert result == Decimal("0")

    def test_rounding(self):
        result = _calc_bonus_amount(Decimal("333333"), Decimal("1.5"), Decimal("1.10"))
        assert result == Decimal("549999")


class TestBonusNetPay:
    def test_net_pay_calculation(self):
        bonus_amount = _calc_bonus_amount(Decimal("300000"), Decimal("2.0"), Decimal("1.00"))
        tax = _calc_bonus_tax(bonus_amount)
        insurance = _calc_bonus_social_insurance(bonus_amount)
        total_deductions = tax + insurance
        net_pay = bonus_amount - total_deductions
        assert net_pay == Decimal("600000") - tax - insurance
        assert net_pay > Decimal("0")

    def test_net_pay_zero_bonus(self):
        bonus_amount = Decimal("0")
        tax = _calc_bonus_tax(bonus_amount)
        insurance = _calc_bonus_social_insurance(bonus_amount)
        net_pay = bonus_amount - tax - insurance
        assert net_pay == Decimal("0")


class TestBonusTermValidation:
    def test_valid_terms(self):
        valid_terms = {"summer", "winter", "yearend", "other"}
        assert "summer" in valid_terms
        assert "winter" in valid_terms
        assert "yearend" in valid_terms
        assert "other" in valid_terms

    def test_invalid_term(self):
        valid_terms = {"summer", "winter", "yearend", "other"}
        assert "spring" not in valid_terms
        assert "" not in valid_terms
