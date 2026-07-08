from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.tax_calculator import TaxCalculator

# 平成28年改正法附則52・53条 / インボイス制度の経過措置
TRANSITIONAL_80_PERCENT_END = date(2026, 9, 30)
TRANSITIONAL_80_PERCENT_START = date(2023, 10, 1)
TRANSITIONAL_50_PERCENT_END = date(2029, 9, 30)
TRANSITIONAL_50_PERCENT_START = date(2026, 10, 1)
TRANSITIONAL_NO_DEDUCTION_START = date(2029, 10, 1)
TRANSITIONAL_80_PERCENT_RATE = Decimal("0.80")
TRANSITIONAL_50_PERCENT_RATE = Decimal("0.50")
TRANSITIONAL_FULL_RATE = Decimal("1.00")
TRANSITIONAL_NO_RATE = Decimal("0.00")


@dataclass(frozen=True)
class InvoiceTransitionalDeductionResult:
    transaction_date: date
    deduction_rate: Decimal
    deductible_tax: Decimal
    non_deductible_tax: Decimal


class InvoiceTransitionalDeductionService:
    @staticmethod
    def _deduction_rate(transaction_date: date) -> Decimal:
        if transaction_date < TRANSITIONAL_80_PERCENT_START:
            return TRANSITIONAL_FULL_RATE
        if transaction_date <= TRANSITIONAL_80_PERCENT_END:
            return TRANSITIONAL_80_PERCENT_RATE
        if transaction_date <= TRANSITIONAL_50_PERCENT_END:
            return TRANSITIONAL_50_PERCENT_RATE
        return TRANSITIONAL_NO_RATE

    @classmethod
    def compute(
        cls,
        purchase_consumption_tax: Decimal,
        transaction_date: date,
    ) -> InvoiceTransitionalDeductionResult:
        if purchase_consumption_tax < 0:
            raise ValueError("purchase_consumption_tax must be non-negative")

        deduction_rate = cls._deduction_rate(transaction_date)
        _, deductible_tax = TaxCalculator.calculate_tax(
            purchase_consumption_tax,
            deduction_rate,
            is_inclusive=False,
        )
        return InvoiceTransitionalDeductionResult(
            transaction_date=transaction_date,
            deduction_rate=deduction_rate,
            deductible_tax=deductible_tax,
            non_deductible_tax=purchase_consumption_tax - deductible_tax,
        )
