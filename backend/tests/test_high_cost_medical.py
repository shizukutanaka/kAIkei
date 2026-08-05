from decimal import Decimal

import pytest

from app.services.high_cost_medical import HighCostMedicalService


def test_category_c_tiered():
    result = HighCostMedicalService.compute(
        total_medical_cost=Decimal("1000000"),
        self_paid=Decimal("300000"),
        income_category="ウ",
    )
    # 80100 + (1000000-267000)*1% = 87430
    assert result.self_pay_limit == Decimal("87430")
    assert result.high_cost_benefit == Decimal("212570")


def test_category_a_tiered():
    result = HighCostMedicalService.compute(
        total_medical_cost=Decimal("1000000"),
        self_paid=Decimal("300000"),
        income_category="ア",
    )
    assert result.self_pay_limit == Decimal("254180")
    assert result.high_cost_benefit == Decimal("45820")


def test_category_d_flat():
    result = HighCostMedicalService.compute(
        total_medical_cost=Decimal("500000"),
        self_paid=Decimal("150000"),
        income_category="エ",
    )
    assert result.self_pay_limit == Decimal("57600")
    assert result.high_cost_benefit == Decimal("92400")


def test_category_e_flat():
    result = HighCostMedicalService.compute(
        total_medical_cost=Decimal("400000"),
        self_paid=Decimal("120000"),
        income_category="オ",
    )
    assert result.self_pay_limit == Decimal("35400")
    assert result.high_cost_benefit == Decimal("84600")


def test_multiple_treatment_uses_lower_limit():
    result = HighCostMedicalService.compute(
        total_medical_cost=Decimal("1000000"),
        self_paid=Decimal("300000"),
        income_category="ウ",
        multiple_treatment=True,
    )
    assert result.self_pay_limit == Decimal("44400")
    assert result.high_cost_benefit == Decimal("255600")


def test_below_limit_no_benefit():
    result = HighCostMedicalService.compute(
        total_medical_cost=Decimal("150000"),
        self_paid=Decimal("50000"),
        income_category="エ",
    )
    assert result.high_cost_benefit == Decimal("0")


def test_over_base_rate_rounds_down():
    result = HighCostMedicalService.compute(
        total_medical_cost=Decimal("267199"),
        self_paid=Decimal("100000"),
        income_category="ウ",
    )
    # over=199 -> 199*0.01=1.99 -> floor 1 -> 80101
    assert result.self_pay_limit == Decimal("80101")


def test_invalid_category_raises():
    with pytest.raises(ValueError):
        HighCostMedicalService.compute(
            total_medical_cost=Decimal("100000"),
            self_paid=Decimal("30000"),
            income_category="X",
        )


def test_negative_self_paid_raises():
    with pytest.raises(ValueError):
        HighCostMedicalService.compute(
            total_medical_cost=Decimal("100000"),
            self_paid=Decimal("-1"),
            income_category="ウ",
        )
