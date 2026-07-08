from decimal import Decimal

import pytest

from app.services.interim_consumption_tax import InterimConsumptionTaxService


class TestInterimConsumptionTaxService:
    def test_boundary_installment_counts(self):
        assert InterimConsumptionTaxService.compute(Decimal("480000")).installment_count == 0
        assert InterimConsumptionTaxService.compute(Decimal("500000")).installment_count == 1
        assert InterimConsumptionTaxService.compute(Decimal("4000000")).installment_count == 1
        assert InterimConsumptionTaxService.compute(Decimal("4000001")).installment_count == 3
        assert InterimConsumptionTaxService.compute(Decimal("6000000")).installment_count == 3
        assert InterimConsumptionTaxService.compute(Decimal("48000000")).installment_count == 3
        assert InterimConsumptionTaxService.compute(Decimal("60000000")).installment_count == 11

    def test_hundred_yen_floor_case(self):
        prior_year_national_tax = Decimal("500001")
        result = InterimConsumptionTaxService.compute(prior_year_national_tax)
        expected = ((prior_year_national_tax * (Decimal("6") / Decimal("12"))) // Decimal("100")) * Decimal("100")

        assert result.installment_count == 1
        assert result.per_installment == expected
        assert result.per_installment == Decimal("250000")
        assert result.total_interim == result.per_installment * Decimal(result.installment_count)

    def test_total_interim_relation(self):
        result = InterimConsumptionTaxService.compute(Decimal("60000000"))
        assert result.total_interim == result.per_installment * Decimal(result.installment_count)
        assert result.annualized_basis == Decimal("60000000")

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            InterimConsumptionTaxService.compute(Decimal("-1"))
