from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from app.services.tax_calculator import TaxCalculator

# 標準税率10%、軽減税率8%、非課税/不課税0%
ALLOWED_INVOICE_TAX_RATES: tuple[Decimal, ...] = (
    Decimal("0.10"),
    Decimal("0.08"),
    Decimal("0.00"),
)


@dataclass(frozen=True)
class InvoiceTaxLine:
    amount: Decimal
    tax_rate: Decimal


@dataclass(frozen=True)
class InvoiceTaxRateBreakdown:
    tax_rate: Decimal
    taxable_base: Decimal
    tax: Decimal


@dataclass(frozen=True)
class InvoiceTaxComputationResult:
    by_rate: list[InvoiceTaxRateBreakdown]
    total_taxable: Decimal
    total_tax: Decimal
    total_amount: Decimal


class InvoiceTaxService:
    @staticmethod
    def _coerce_line(line: InvoiceTaxLine | tuple[Decimal, Decimal] | object) -> tuple[Decimal, Decimal]:
        try:
            return line.amount, line.tax_rate
        except AttributeError:
            amount, tax_rate = line  # type: ignore[misc]
            return amount, tax_rate

    @classmethod
    def compute_invoice_tax(
        cls,
        lines: list[InvoiceTaxLine | tuple[Decimal, Decimal]],
    ) -> InvoiceTaxComputationResult:
        if not lines:
            raise ValueError("lines must not be empty")

        grouped: dict[Decimal, Decimal] = defaultdict(lambda: Decimal("0"))
        for line in lines:
            amount, tax_rate = cls._coerce_line(line)
            if amount < 0:
                raise ValueError("amount must be non-negative")
            if tax_rate not in ALLOWED_INVOICE_TAX_RATES:
                raise ValueError("unsupported tax_rate")
            grouped[tax_rate] += amount

        by_rate: list[InvoiceTaxRateBreakdown] = []
        total_taxable = Decimal("0")
        total_tax = Decimal("0")

        for tax_rate in sorted(grouped):
            taxable_base = grouped[tax_rate]
            _, tax = TaxCalculator.calculate_tax(taxable_base, tax_rate, is_inclusive=False)
            by_rate.append(
                InvoiceTaxRateBreakdown(
                    tax_rate=tax_rate,
                    taxable_base=taxable_base,
                    tax=tax,
                )
            )
            total_taxable += taxable_base
            total_tax += tax

        total_amount = total_taxable + total_tax
        return InvoiceTaxComputationResult(
            by_rate=by_rate,
            total_taxable=total_taxable,
            total_tax=total_tax,
            total_amount=total_amount,
        )
