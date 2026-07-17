from decimal import Decimal

import pytest

from app.services.social_insurance import SocialInsurancePremiumService


class TestSocialInsurancePremiumService:
    def test_compute_defaults_without_care(self):
        result = SocialInsurancePremiumService.compute(Decimal("300000"))

        assert result.standard_monthly_remuneration == Decimal("300000")
        assert result.pension.total == Decimal("54900")
        assert result.pension.employee == Decimal("27450")
        assert result.pension.employer == Decimal("27450")
        assert result.health.total == Decimal("29940")
        assert result.health.employee == Decimal("14970")
        assert result.health.employer == Decimal("14970")
        assert result.care.total == Decimal("0")
        assert result.care.employee == Decimal("0")
        assert result.care.employer == Decimal("0")
        assert result.total_employee == Decimal("42420")
        assert result.total_employer == Decimal("42420")
        assert result.total_premium == Decimal("84840")

    def test_compute_with_care_applicable(self):
        result = SocialInsurancePremiumService.compute(
            Decimal("300000"),
            care_applicable=True,
        )

        assert result.care.total == Decimal("4800")
        assert result.care.employee == Decimal("2400")
        assert result.care.employer == Decimal("2400")
        assert result.total_employee == Decimal("44820")
        assert result.total_employer == Decimal("44820")
        assert result.total_premium == Decimal("89640")

    def test_half_down_rounding_boundary(self):
        down = SocialInsurancePremiumService.compute(
            Decimal("1000"),
            health_rate=Decimal("0.201"),
        )
        up = SocialInsurancePremiumService.compute(
            Decimal("1000"),
            health_rate=Decimal("0.2012"),
        )

        assert down.health.total == Decimal("201")
        assert down.health.employee == Decimal("100")
        assert down.health.employer == Decimal("101")
        assert up.health.total == Decimal("201.2")
        assert up.health.employee == Decimal("101")
        assert up.health.employer == Decimal("100.2")

    def test_negative_inputs_raise(self):
        with pytest.raises(ValueError):
            SocialInsurancePremiumService.compute(Decimal("-1"))
        with pytest.raises(ValueError):
            SocialInsurancePremiumService.compute(
                Decimal("1"),
                health_rate=Decimal("-0.1"),
            )
        with pytest.raises(ValueError):
            SocialInsurancePremiumService.compute(
                Decimal("1"),
                care_rate=Decimal("-0.1"),
            )

    def test_compute_bonus_defaults_without_care(self):
        result = SocialInsurancePremiumService.compute_bonus(
            Decimal("500000"),
            Decimal("500000"),
        )

        assert result.health.total == Decimal("49900")
        assert result.health.employee == Decimal("24950")
        assert result.health.employer == Decimal("24950")
        assert result.pension.total == Decimal("91500")
        assert result.pension.employee == Decimal("45750")
        assert result.pension.employer == Decimal("45750")
        assert result.care.total == Decimal("0")
        assert result.total_employee == Decimal("70700")
        assert result.total_employer == Decimal("70700")
        assert result.total_premium == Decimal("141400")

    def test_compute_bonus_differing_bases_and_care(self):
        result = SocialInsurancePremiumService.compute_bonus(
            Decimal("5730000"),
            Decimal("1500000"),
            care_applicable=True,
        )

        assert result.health.total == Decimal("571854")
        assert result.health.employee == Decimal("285927")
        assert result.health.employer == Decimal("285927")
        assert result.care.total == Decimal("91680")
        assert result.care.employee == Decimal("45840")
        assert result.care.employer == Decimal("45840")
        assert result.pension.total == Decimal("274500")
        assert result.pension.employee == Decimal("137250")
        assert result.pension.employer == Decimal("137250")
        assert result.total_employee == Decimal("469017")
        assert result.total_employer == Decimal("469017")
        assert result.total_premium == Decimal("938034")

    def test_compute_bonus_negative_inputs_raise(self):
        with pytest.raises(ValueError):
            SocialInsurancePremiumService.compute_bonus(Decimal("-1"), Decimal("1"))
        with pytest.raises(ValueError):
            SocialInsurancePremiumService.compute_bonus(Decimal("1"), Decimal("-1"))

    def test_monthly_compute_regression_after_split_helper(self):
        result = SocialInsurancePremiumService.compute(Decimal("300000"))

        assert result.pension.total == Decimal("54900")
        assert result.health.total == Decimal("29940")
        assert result.total_employee == Decimal("42420")
