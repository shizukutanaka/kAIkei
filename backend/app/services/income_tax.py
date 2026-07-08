from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

# 所得税法89条 / 課税される所得金額の速算表（千円未満切捨）
INCOME_TAX_BRACKETS: tuple[tuple[Decimal, Decimal, Decimal], ...] = (
    (Decimal("1950000"), Decimal("0.05"), Decimal("0")),
    (Decimal("3300000"), Decimal("0.10"), Decimal("97500")),
    (Decimal("6950000"), Decimal("0.20"), Decimal("427500")),
    (Decimal("9000000"), Decimal("0.23"), Decimal("636000")),
    (Decimal("18000000"), Decimal("0.33"), Decimal("1536000")),
    (Decimal("40000000"), Decimal("0.40"), Decimal("2796000")),
)
INCOME_TAX_RATE_TOP = Decimal("0.45")
INCOME_TAX_DEDUCTION_TOP = Decimal("4796000")
INCOME_TAX_ROUNDING_UNIT = Decimal("1E3")


class IncomeTaxService:
    @staticmethod
    def compute(taxable_income: Decimal) -> Decimal:
        if taxable_income < 0:
            raise ValueError("taxable_income must be non-negative")

        rounded_taxable_income = (taxable_income // INCOME_TAX_ROUNDING_UNIT) * INCOME_TAX_ROUNDING_UNIT

        for upper_bound, rate, deduction in INCOME_TAX_BRACKETS:
            if rounded_taxable_income <= upper_bound:
                tax = rounded_taxable_income * rate - deduction
                return max(tax.quantize(Decimal("1"), rounding=ROUND_DOWN), Decimal("0"))

        tax = rounded_taxable_income * INCOME_TAX_RATE_TOP - INCOME_TAX_DEDUCTION_TOP
        return max(tax.quantize(Decimal("1"), rounding=ROUND_DOWN), Decimal("0"))
