from decimal import Decimal

import pytest

from app.services.bonus_withholding_tax import BonusWithholdingTaxService


class TestBonusWithholdingTaxService:
    def test_normal_rate_table_case(self):
        result = BonusWithholdingTaxService.compute(
            Decimal("400000"),
            Decimal("0.1021"),
            Decimal("300000"),
        )

        assert result.withholding_tax == Decimal("40840")
        assert result.requires_monthly_table is False
        assert result.reason == "rate_table"

    def test_no_prior_month_salary(self):
        result = BonusWithholdingTaxService.compute(
            Decimal("400000"),
            Decimal("0.1021"),
            None,
        )

        assert result.withholding_tax is None
        assert result.requires_monthly_table is True
        assert result.reason == "no_prior_month_salary"

    def test_exceeds_ten_x_prior_salary(self):
        result = BonusWithholdingTaxService.compute(
            Decimal("400000"),
            Decimal("0.1021"),
            Decimal("30000"),
        )

        assert result.withholding_tax is None
        assert result.requires_monthly_table is True
        assert result.reason == "bonus_exceeds_10x_prior_salary"

    def test_exactly_ten_x_uses_rate_table(self):
        result = BonusWithholdingTaxService.compute(
            Decimal("400000"),
            Decimal("0.1021"),
            Decimal("40000"),
        )

        assert result.withholding_tax == Decimal("40840")
        assert result.requires_monthly_table is False
        assert result.reason == "rate_table"

    def test_round_down_boundary(self):
        result = BonusWithholdingTaxService.compute(
            Decimal("100"),
            Decimal("0.125"),
            Decimal("20"),
        )

        assert result.withholding_tax == Decimal("12")

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            BonusWithholdingTaxService.compute(Decimal("-1"), Decimal("0.1"), Decimal("1"))
        with pytest.raises(ValueError):
            BonusWithholdingTaxService.compute(Decimal("1"), Decimal("-0.1"), Decimal("1"))
        with pytest.raises(ValueError):
            BonusWithholdingTaxService.compute(Decimal("1"), Decimal("1.5"), Decimal("1"))
        with pytest.raises(ValueError):
            BonusWithholdingTaxService.compute(Decimal("1"), Decimal("0.1"), Decimal("-1"))
