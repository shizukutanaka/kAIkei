from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.tax_calculator import TaxCalculator

# インボイス発行事業者の負担軽減措置 / 2割特例
SPECIAL_TWENTY_PERCENT_RATE = Decimal("0.20")


@dataclass(frozen=True)
class SpecialTwentyPercentConsumptionTaxResult:
    sales_consumption_tax: Decimal
    payable_tax: Decimal
    special_deduction: Decimal


class SpecialTwentyPercentConsumptionTaxService:
    @staticmethod
    def compute(sales_consumption_tax: Decimal) -> SpecialTwentyPercentConsumptionTaxResult:
        if sales_consumption_tax < 0:
            raise ValueError("sales_consumption_tax must be non-negative")

        _, payable_tax = TaxCalculator.calculate_tax(sales_consumption_tax, SPECIAL_TWENTY_PERCENT_RATE, is_inclusive=False)
        return SpecialTwentyPercentConsumptionTaxResult(
            sales_consumption_tax=sales_consumption_tax,
            payable_tax=payable_tax,
            special_deduction=sales_consumption_tax - payable_tax,
        )
