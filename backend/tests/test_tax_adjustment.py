from decimal import Decimal

import pytest

from app.services.tax_adjustment import (
    AdjustmentResult,
    AdjustmentRuleSpec,
    build_result,
    compute_adjustment_amount,
    compute_taxable_income,
)


def _spec(method, **kw):
    base = dict(
        rule_id="r1",
        name="rule",
        adjustment_type="addition",
        calculation_method=method,
    )
    base.update(kw)
    return AdjustmentRuleSpec(**base)


class TestComputeAdjustmentAmount:
    def test_fixed(self):
        spec = _spec("fixed", fixed_amount=Decimal("50000"))
        assert compute_adjustment_amount(spec) == Decimal("50000")

    def test_rate_truncates_to_yen(self):
        spec = _spec("rate", rate=Decimal("0.1000"))
        # 333円 × 10% = 33.3 → 切捨て 33
        assert compute_adjustment_amount(spec, Decimal("333")) == Decimal("33")

    def test_excess_over_limit_positive(self):
        # 交際費 1,000,000 に対し限度 800,000 → 超過 200,000
        spec = _spec("excess_over_limit", limit_amount=Decimal("800000"))
        assert compute_adjustment_amount(spec, Decimal("1000000")) == Decimal("200000")

    def test_excess_over_limit_within_limit_is_zero(self):
        spec = _spec("excess_over_limit", limit_amount=Decimal("800000"))
        assert compute_adjustment_amount(spec, Decimal("500000")) == Decimal("0")

    def test_negative_clamped_to_zero(self):
        spec = _spec("fixed", fixed_amount=Decimal("-100"))
        assert compute_adjustment_amount(spec) == Decimal("0")

    def test_unknown_method_raises(self):
        spec = _spec("bogus")
        with pytest.raises(ValueError):
            compute_adjustment_amount(spec, Decimal("100"))


class TestComputeTaxableIncome:
    def test_additions_increase_income(self):
        results = [
            AdjustmentResult("r1", "交際費超過", "addition", Decimal("200000")),
            AdjustmentResult("r2", "減価償却超過", "addition", Decimal("50000")),
        ]
        assert compute_taxable_income(Decimal("1000000"), results) == Decimal("1250000")

    def test_subtractions_decrease_income(self):
        results = [
            AdjustmentResult("r1", "受取配当益金不算入", "subtraction", Decimal("100000")),
        ]
        assert compute_taxable_income(Decimal("1000000"), results) == Decimal("900000")

    def test_mixed(self):
        results = [
            AdjustmentResult("r1", "加算", "addition", Decimal("300000")),
            AdjustmentResult("r2", "減算", "subtraction", Decimal("120000")),
        ]
        assert compute_taxable_income(Decimal("1000000"), results) == Decimal("1180000")

    def test_no_adjustments(self):
        assert compute_taxable_income(Decimal("1000000"), []) == Decimal("1000000")


class TestBuildResult:
    def test_carries_type_and_amount(self):
        spec = _spec("excess_over_limit", adjustment_type="addition", limit_amount=Decimal("800000"), name="交際費")
        result = build_result(spec, Decimal("1000000"))
        assert result.adjustment_type == "addition"
        assert result.amount == Decimal("200000")
        assert result.name == "交際費"
