from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# 消費税法42条 / 前年度の国税分消費税額に基づく中間申告・中間納付税額
INTERIM_CONSUMPTION_TAX_THRESHOLD_1 = Decimal("480000")
INTERIM_CONSUMPTION_TAX_THRESHOLD_2 = Decimal("4000000")
INTERIM_CONSUMPTION_TAX_THRESHOLD_3 = Decimal("48000000")
INTERIM_CONSUMPTION_TAX_FRACTION_1 = Decimal("6") / Decimal("12")
INTERIM_CONSUMPTION_TAX_FRACTION_3 = Decimal("3") / Decimal("12")
INTERIM_CONSUMPTION_TAX_FRACTION_11 = Decimal("1") / Decimal("12")
INTERIM_CONSUMPTION_TAX_ROUNDING_UNIT = Decimal("100")


@dataclass(frozen=True)
class InterimConsumptionTaxResult:
    installment_count: int
    per_installment: Decimal
    total_interim: Decimal
    annualized_basis: Decimal


class InterimConsumptionTaxService:
    @staticmethod
    def _floor_to_100(amount: Decimal) -> Decimal:
        return (amount // INTERIM_CONSUMPTION_TAX_ROUNDING_UNIT) * INTERIM_CONSUMPTION_TAX_ROUNDING_UNIT

    @classmethod
    def compute(cls, prior_year_national_tax: Decimal) -> InterimConsumptionTaxResult:
        if prior_year_national_tax < 0:
            raise ValueError("prior_year_national_tax must be non-negative")

        if prior_year_national_tax <= INTERIM_CONSUMPTION_TAX_THRESHOLD_1:
            installment_count = 0
            per_installment = Decimal("0")
        elif prior_year_national_tax <= INTERIM_CONSUMPTION_TAX_THRESHOLD_2:
            installment_count = 1
            per_installment = cls._floor_to_100(prior_year_national_tax * INTERIM_CONSUMPTION_TAX_FRACTION_1)
        elif prior_year_national_tax <= INTERIM_CONSUMPTION_TAX_THRESHOLD_3:
            installment_count = 3
            per_installment = cls._floor_to_100(prior_year_national_tax * INTERIM_CONSUMPTION_TAX_FRACTION_3)
        else:
            installment_count = 11
            per_installment = cls._floor_to_100(prior_year_national_tax * INTERIM_CONSUMPTION_TAX_FRACTION_11)

        total_interim = per_installment * Decimal(installment_count)
        return InterimConsumptionTaxResult(
            installment_count=installment_count,
            per_installment=per_installment,
            total_interim=total_interim,
            annualized_basis=prior_year_national_tax,
        )
