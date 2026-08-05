from decimal import Decimal

import pytest

from app.services.retirement_income_tax import RetirementIncomeTaxService


def test_over_20_years_normal_half_taxation():
    result = RetirementIncomeTaxService.compute(
        severance_pay=Decimal("20000000"), months_of_service=360
    )
    assert result.years_of_service == 30
    assert result.retirement_income_deduction == Decimal("15000000")
    assert result.taxable_base == Decimal("5000000")
    assert result.taxable_retirement_income == Decimal("2500000")
    assert result.income_tax_base == Decimal("152500")
    assert result.withholding_tax == Decimal("155702")


def test_deduction_below_20_years_and_minimum():
    result = RetirementIncomeTaxService.compute(
        severance_pay=Decimal("3000000"), months_of_service=120
    )
    assert result.years_of_service == 10
    assert result.retirement_income_deduction == Decimal("4000000")
    assert result.taxable_base == Decimal("0")
    assert result.withholding_tax == Decimal("0")


def test_year_rounding_up():
    result = RetirementIncomeTaxService.compute(
        severance_pay=Decimal("1000000"), months_of_service=241
    )
    assert result.years_of_service == 21
    assert result.retirement_income_deduction == Decimal("8700000")


def test_specified_officer_no_half():
    result = RetirementIncomeTaxService.compute(
        severance_pay=Decimal("8000000"), months_of_service=60, is_specified_officer_5yr_or_less=True
    )
    assert result.taxable_base == Decimal("6000000")
    assert result.taxable_retirement_income == Decimal("6000000")
    assert result.income_tax_base == Decimal("772500")
    assert result.withholding_tax == Decimal("788722")


def test_short_term_partial_half():
    result = RetirementIncomeTaxService.compute(
        severance_pay=Decimal("8000000"), months_of_service=60, is_short_term_5yr_or_less=True
    )
    assert result.taxable_base == Decimal("6000000")
    assert result.taxable_retirement_income == Decimal("4500000")
    assert result.income_tax_base == Decimal("472500")
    assert result.withholding_tax == Decimal("482422")


def test_no_statement_flat_rate():
    result = RetirementIncomeTaxService.compute(
        severance_pay=Decimal("5000000"), months_of_service=120, statement_submitted=False
    )
    assert result.statement_submitted is False
    assert result.withholding_tax == Decimal("1021000")


def test_conflicting_flags_raise():
    with pytest.raises(ValueError):
        RetirementIncomeTaxService.compute(
            severance_pay=Decimal("1000000"),
            months_of_service=60,
            is_specified_officer_5yr_or_less=True,
            is_short_term_5yr_or_less=True,
        )


def test_five_year_flag_requires_short_tenure():
    with pytest.raises(ValueError):
        RetirementIncomeTaxService.compute(
            severance_pay=Decimal("1000000"),
            months_of_service=120,
            is_specified_officer_5yr_or_less=True,
        )


def test_negative_severance_raises():
    with pytest.raises(ValueError):
        RetirementIncomeTaxService.compute(severance_pay=Decimal("-1"), months_of_service=12)
