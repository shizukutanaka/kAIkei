from decimal import Decimal

import pytest

from app.services.bonus_employment_insurance import BonusEmploymentInsuranceService
from app.services.labor_insurance import BUSINESS_TYPE_GENERAL


class TestBonusEmploymentInsuranceService:
    def test_general_bonus_compute(self):
        result = BonusEmploymentInsuranceService.compute(
            Decimal("500000"),
            BUSINESS_TYPE_GENERAL,
        )

        assert result.employee_rate == Decimal("0.006")
        assert result.employer_rate == Decimal("0.0095")
        assert result.employee_premium == Decimal("3000")
        assert result.employer_premium == Decimal("4750")
        assert result.total_premium == Decimal("7750")

    def test_half_down_boundary(self):
        result = BonusEmploymentInsuranceService.compute(
            Decimal("1000"),
            BUSINESS_TYPE_GENERAL,
        )

        assert result.employee_premium == Decimal("6")
        assert result.employer_premium == Decimal("9")
        assert result.total_premium == Decimal("15")

    def test_unsupported_business_type_raises(self):
        with pytest.raises(ValueError):
            BonusEmploymentInsuranceService.compute(Decimal("1"), "unsupported")

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            BonusEmploymentInsuranceService.compute(Decimal("-1"), BUSINESS_TYPE_GENERAL)
