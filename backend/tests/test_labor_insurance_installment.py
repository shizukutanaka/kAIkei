from decimal import Decimal

import pytest

from app.services.labor_insurance_installment import LaborInsuranceInstallmentService


class TestLaborInsuranceInstallmentService:
    def test_eligible_by_amount(self):
        result = LaborInsuranceInstallmentService.compute(
            Decimal("900000"),
            both_insurances=True,
        )

        assert result.threshold == Decimal("400000")
        assert result.eligible is True
        assert result.installment_count == 3
        assert result.installments == [
            Decimal("300000"),
            Decimal("300000"),
            Decimal("300000"),
        ]
        assert sum(result.installments, Decimal("0")) == Decimal("900000")

    def test_remainder_to_first_installment(self):
        result = LaborInsuranceInstallmentService.compute(Decimal("1000000"))

        assert result.installment_count == 3
        assert result.installments == [
            Decimal("333334"),
            Decimal("333333"),
            Decimal("333333"),
        ]
        assert sum(result.installments, Decimal("0")) == Decimal("1000000")

    def test_not_eligible_becomes_single_installment(self):
        result = LaborInsuranceInstallmentService.compute(
            Decimal("300000"),
            both_insurances=True,
            entrusted=False,
        )

        assert result.threshold == Decimal("400000")
        assert result.eligible is False
        assert result.installment_count == 1
        assert result.installments == [Decimal("300000")]

    def test_one_insurance_threshold(self):
        result = LaborInsuranceInstallmentService.compute(
            Decimal("250000"),
            both_insurances=False,
        )

        assert result.threshold == Decimal("200000")
        assert result.eligible is True
        assert result.installment_count == 3
        assert sum(result.installments, Decimal("0")) == Decimal("250000")

    def test_entrusted_overrides_amount(self):
        result = LaborInsuranceInstallmentService.compute(
            Decimal("100000"),
            entrusted=True,
        )

        assert result.eligible is True
        assert result.installment_count == 3
        assert sum(result.installments, Decimal("0")) == Decimal("100000")

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            LaborInsuranceInstallmentService.compute(Decimal("-1"))
