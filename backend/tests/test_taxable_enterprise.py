from decimal import Decimal

import pytest

from app.services.taxable_enterprise import TaxableEnterpriseJudgmentService


class TestTaxableEnterpriseJudgmentService:
    def test_base_period_over_threshold_is_taxable(self):
        result = TaxableEnterpriseJudgmentService.judge(
            Decimal("12000000"),
            Decimal("100000"),
            Decimal("100000"),
        )
        assert result.is_taxable is True
        assert result.basis == "base_period"

    def test_specific_period_and_semantics(self):
        result = TaxableEnterpriseJudgmentService.judge(
            Decimal("9000000"),
            Decimal("12000000"),
            Decimal("12000000"),
        )
        assert result.is_taxable is True
        assert result.basis == "specific_period"

    def test_specific_period_sales_only_not_taxable(self):
        result = TaxableEnterpriseJudgmentService.judge(
            Decimal("9000000"),
            Decimal("12000000"),
            Decimal("10000000"),
        )
        assert result.is_taxable is False
        assert result.basis == "exempt"

    def test_all_below_threshold_exempt(self):
        result = TaxableEnterpriseJudgmentService.judge(
            Decimal("1000000"),
            Decimal("9999999"),
            Decimal("9999999"),
        )
        assert result.is_taxable is False
        assert result.basis == "exempt"

    def test_exact_boundary_not_triggered(self):
        result = TaxableEnterpriseJudgmentService.judge(
            Decimal("10000000"),
            Decimal("10000000"),
            Decimal("10000000"),
        )
        assert result.is_taxable is False
        assert result.basis == "exempt"

    def test_negative_input_raises(self):
        with pytest.raises(ValueError):
            TaxableEnterpriseJudgmentService.judge(Decimal("-1"), Decimal("0"), Decimal("0"))
