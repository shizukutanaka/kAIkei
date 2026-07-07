from decimal import Decimal

import pytest

from app.services.bonus_net_pay import BonusNetPayService
from app.services.labor_insurance import BUSINESS_TYPE_GENERAL


class TestBonusNetPayService:
    def test_normal_integrated_case(self):
        result = BonusNetPayService.compute(
            gross_bonus=Decimal("600000"),
            business_type=BUSINESS_TYPE_GENERAL,
            health_rate=Decimal("0.0998"),
            care_rate=Decimal("0.016"),
            care_applicable=False,
            bonus_tax_rate=Decimal("0.1021"),
            prior_month_salary_after_social_insurance=Decimal("600000"),
            cumulative_health_standard_bonus_ytd=Decimal("0"),
        )

        assert result.standard_bonus == Decimal("600000")
        assert result.health_standard_bonus == Decimal("600000")
        assert result.pension_standard_bonus == Decimal("600000")
        assert result.social_insurance.health.employee == Decimal("29940")
        assert result.social_insurance.pension.employee == Decimal("54900")
        assert result.social_insurance.care.employee == Decimal("0")
        assert result.social_insurance.total_employee == Decimal("84840")
        assert result.employment_insurance_employee == Decimal("3600")
        assert result.bonus_after_social_insurance == Decimal("511560")
        assert result.withholding_tax == Decimal("52230")
        assert result.requires_monthly_table is False
        assert result.reason == "rate_table"
        assert result.total_employee_deductions == Decimal("88440")
        assert result.net_pay == Decimal("459330")

    def test_pension_cap(self):
        result = BonusNetPayService.compute(
            gross_bonus=Decimal("2000000"),
            business_type=BUSINESS_TYPE_GENERAL,
            health_rate=Decimal("0.0998"),
            care_rate=Decimal("0.016"),
            care_applicable=False,
            bonus_tax_rate=Decimal("0"),
            prior_month_salary_after_social_insurance=Decimal("1000000"),
            cumulative_health_standard_bonus_ytd=Decimal("0"),
        )

        assert result.health_standard_bonus == Decimal("2000000")
        assert result.pension_standard_bonus == Decimal("1500000")
        assert result.social_insurance.health.employee == Decimal("99800")
        assert result.social_insurance.pension.employee == Decimal("137250")
        assert result.employment_insurance_employee == Decimal("12000")
        assert result.bonus_after_social_insurance == Decimal("1750950")
        assert result.net_pay == Decimal("1750950")

    def test_health_ytd_cap(self):
        result = BonusNetPayService.compute(
            gross_bonus=Decimal("100000"),
            business_type=BUSINESS_TYPE_GENERAL,
            health_rate=Decimal("0.0998"),
            care_rate=Decimal("0.016"),
            care_applicable=False,
            bonus_tax_rate=Decimal("0"),
            prior_month_salary_after_social_insurance=Decimal("100000"),
            cumulative_health_standard_bonus_ytd=Decimal("5700000"),
        )

        assert result.health_standard_bonus == Decimal("30000")
        assert result.pension_standard_bonus == Decimal("100000")
        assert result.social_insurance.health.employee == Decimal("1497")
        assert result.social_insurance.pension.employee == Decimal("9150")
        assert result.employment_insurance_employee == Decimal("600")
        assert result.total_employee_deductions == Decimal("11247")
        assert result.bonus_after_social_insurance == Decimal("88753")
        assert result.net_pay == Decimal("88753")

    def test_requires_monthly_table_propagates(self):
        result = BonusNetPayService.compute(
            gross_bonus=Decimal("600000"),
            business_type=BUSINESS_TYPE_GENERAL,
            health_rate=Decimal("0.0998"),
            care_rate=Decimal("0.016"),
            care_applicable=False,
            bonus_tax_rate=Decimal("0.1021"),
            prior_month_salary_after_social_insurance=None,
            cumulative_health_standard_bonus_ytd=Decimal("0"),
        )

        assert result.requires_monthly_table is True
        assert result.reason == "no_prior_month_salary"
        assert result.withholding_tax is None
        assert result.net_pay is None

    def test_negative_gross_raises(self):
        with pytest.raises(ValueError):
            BonusNetPayService.compute(
                gross_bonus=Decimal("-1"),
                business_type=BUSINESS_TYPE_GENERAL,
                bonus_tax_rate=Decimal("0.1"),
            )
