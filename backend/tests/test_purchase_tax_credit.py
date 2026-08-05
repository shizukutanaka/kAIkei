from decimal import Decimal

import pytest

from app.services.purchase_tax_credit import PurchaseTaxCreditService


def test_full_deduction_under_95_percent_rule():
    # ratio = 40,000,000 / 40,500,000 >= 0.95, sales <= 5億 -> full deduction
    result = PurchaseTaxCreditService.compute(
        taxable_sales=Decimal("40000000"),
        non_taxable_sales=Decimal("500000"),
        input_tax_taxable_only=Decimal("1000000"),
        input_tax_common=Decimal("500000"),
        input_tax_nontaxable_only=Decimal("100000"),
    )
    assert result.full_deduction is True
    assert result.input_tax_total == Decimal("1600000")
    assert result.individual_method_credit == Decimal("1600000")
    assert result.proportional_method_credit == Decimal("1600000")


def test_no_full_deduction_when_sales_over_500m():
    # ratio 100% but sales > 5億 -> no full deduction, but ratio 1.0 keeps full credit
    result = PurchaseTaxCreditService.compute(
        taxable_sales=Decimal("600000000"),
        non_taxable_sales=Decimal("0"),
        input_tax_taxable_only=Decimal("1000000"),
        input_tax_common=Decimal("500000"),
    )
    assert result.full_deduction is False
    assert result.taxable_ratio == Decimal("1")
    # common * 1.0 = 500000
    assert result.individual_method_credit == Decimal("1500000")
    assert result.proportional_method_credit == Decimal("1500000")


def test_individual_method_ratio_applied_to_common_only():
    # ratio = 60,000,000 / 100,000,000 = 0.6
    result = PurchaseTaxCreditService.compute(
        taxable_sales=Decimal("60000000"),
        non_taxable_sales=Decimal("40000000"),
        input_tax_taxable_only=Decimal("1000000"),
        input_tax_common=Decimal("500000"),
        input_tax_nontaxable_only=Decimal("200000"),
    )
    assert result.full_deduction is False
    assert result.taxable_ratio == Decimal("0.6")
    # individual = 1,000,000 + floor(500,000 * 0.6 = 300,000) = 1,300,000
    assert result.individual_method_credit == Decimal("1300000")
    # proportional = floor(1,700,000 * 0.6 = 1,020,000) = 1,020,000
    assert result.proportional_method_credit == Decimal("1020000")


def test_rounding_down_on_multiplied_portion():
    # ratio = 1/3
    result = PurchaseTaxCreditService.compute(
        taxable_sales=Decimal("10000000"),
        non_taxable_sales=Decimal("20000000"),
        input_tax_taxable_only=Decimal("0"),
        input_tax_common=Decimal("100000"),
    )
    # common * 1/3 = 33333.33 -> floor 33333
    assert result.individual_method_credit == Decimal("33333")
    assert result.proportional_method_credit == Decimal("33333")


def test_zero_total_sales_raises():
    with pytest.raises(ValueError):
        PurchaseTaxCreditService.compute(
            taxable_sales=Decimal("0"),
            non_taxable_sales=Decimal("0"),
            input_tax_taxable_only=Decimal("100000"),
            input_tax_common=Decimal("0"),
        )


def test_negative_input_tax_raises():
    with pytest.raises(ValueError):
        PurchaseTaxCreditService.compute(
            taxable_sales=Decimal("1000000"),
            non_taxable_sales=Decimal("0"),
            input_tax_taxable_only=Decimal("-1"),
            input_tax_common=Decimal("0"),
        )
