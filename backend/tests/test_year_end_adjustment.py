from decimal import Decimal

import pytest

from app.services.year_end_adjustment import YearEndAdjustmentService


def test_refund_case():
    result = YearEndAdjustmentService.compute(
        annual_gross_salary=Decimal("5000000"),
        total_income_deductions=Decimal("1200000"),
        withheld_tax_total=Decimal("150000"),
    )
    assert result.salary_income_deduction == Decimal("1440000")
    assert result.salary_income == Decimal("3560000")
    assert result.taxable_income == Decimal("2360000")
    assert result.calculated_income_tax == Decimal("138500")
    assert result.year_tax == Decimal("141400")
    assert result.refund == Decimal("8600")
    assert result.additional_collection == Decimal("0")


def test_additional_collection_case():
    result = YearEndAdjustmentService.compute(
        annual_gross_salary=Decimal("5000000"),
        total_income_deductions=Decimal("1200000"),
        withheld_tax_total=Decimal("130000"),
    )
    assert result.year_tax == Decimal("141400")
    assert result.refund == Decimal("0")
    assert result.additional_collection == Decimal("11400")


def test_housing_loan_credit_reduces_tax():
    result = YearEndAdjustmentService.compute(
        annual_gross_salary=Decimal("5000000"),
        total_income_deductions=Decimal("1200000"),
        withheld_tax_total=Decimal("150000"),
        housing_loan_credit=Decimal("50000"),
    )
    assert result.year_adjusted_income_tax == Decimal("88500")
    assert result.year_tax == Decimal("90300")
    assert result.refund == Decimal("59700")


def test_credit_cannot_go_negative():
    result = YearEndAdjustmentService.compute(
        annual_gross_salary=Decimal("5000000"),
        total_income_deductions=Decimal("1200000"),
        withheld_tax_total=Decimal("138500"),
        housing_loan_credit=Decimal("500000"),
    )
    assert result.year_adjusted_income_tax == Decimal("0")
    assert result.year_tax == Decimal("0")
    assert result.refund == Decimal("138500")


def test_deductions_exceed_income_zero_tax():
    result = YearEndAdjustmentService.compute(
        annual_gross_salary=Decimal("2000000"),
        total_income_deductions=Decimal("2000000"),
        withheld_tax_total=Decimal("0"),
    )
    assert result.taxable_income == Decimal("0")
    assert result.year_tax == Decimal("0")


def test_negative_input_raises():
    with pytest.raises(ValueError):
        YearEndAdjustmentService.compute(
            annual_gross_salary=Decimal("-1"),
            total_income_deductions=Decimal("0"),
            withheld_tax_total=Decimal("0"),
        )
