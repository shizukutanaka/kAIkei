from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.tax_calculator import TaxCalculator

# 地方税法72条の83 / 地方消費税は国税分消費税額を課税標準とする（22/78 ≒ 2.2/7.8）
LOCAL_CONSUMPTION_TAX_RATE = Decimal("22") / Decimal("78")


@dataclass(frozen=True)
class LocalConsumptionTaxResult:
    national_tax: Decimal
    local_tax: Decimal
    total_tax: Decimal


class LocalConsumptionTaxService:
    @staticmethod
    def compute(national_tax: Decimal) -> LocalConsumptionTaxResult:
        if national_tax < 0:
            raise ValueError("national_tax must be non-negative")

        _, local_tax = TaxCalculator.calculate_tax(national_tax, LOCAL_CONSUMPTION_TAX_RATE, is_inclusive=False)
        return LocalConsumptionTaxResult(
            national_tax=national_tax,
            local_tax=local_tax,
            total_tax=national_tax + local_tax,
        )
