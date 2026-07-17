from decimal import Decimal

import pytest

from app.services.interim_corporate_tax import InterimCorporateTaxService


class TestInterimCorporateTaxService:
    def test_normal_12_month_case(self):
        result = InterimCorporateTaxService.compute(Decimal("1000000"))
        assert result.interim_tax == Decimal("500000")
        assert result.filing_required is True
        assert result.prior_period_months == 12

    def test_threshold_cases(self):
        result = InterimCorporateTaxService.compute(Decimal("200000"))
        assert result.interim_tax == Decimal("100000")
        assert result.filing_required is False

        result = InterimCorporateTaxService.compute(Decimal("150000"))
        assert result.interim_tax == Decimal("75000")
        assert result.filing_required is False

    def test_short_prior_period(self):
        result = InterimCorporateTaxService.compute(Decimal("600000"), prior_period_months=6)
        assert result.interim_tax == Decimal("600000")
        assert result.filing_required is True
        assert result.prior_period_months == 6

    def test_hundred_yen_floor_case(self):
        prior_year_corporate_tax = Decimal("333333")
        result = InterimCorporateTaxService.compute(prior_year_corporate_tax)
        expected = ((prior_year_corporate_tax * Decimal("6") / Decimal("12")) // Decimal("100")) * Decimal("100")

        assert result.interim_tax == expected
        assert result.interim_tax == Decimal("166600")
        assert result.filing_required is True

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            InterimCorporateTaxService.compute(Decimal("-1"))
        with pytest.raises(ValueError):
            InterimCorporateTaxService.compute(Decimal("100000"), prior_period_months=0)
        with pytest.raises(ValueError):
            InterimCorporateTaxService.compute(Decimal("100000"), prior_period_months=13)
