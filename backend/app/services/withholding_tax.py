from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

# 所得税法204条 / 復興特別所得税: 士業報酬・原稿料・講演料等の一般区分
WITHHOLDING_TAX_RATE_UP_TO_THRESHOLD = Decimal("0.1021")
WITHHOLDING_TAX_RATE_ABOVE_THRESHOLD = Decimal("0.2042")
WITHHOLDING_TAX_THRESHOLD = Decimal("1000000")


class WithholdingTaxService:
    @staticmethod
    def compute_professional_fee(amount: Decimal) -> Decimal:
        if amount < 0:
            raise ValueError("amount must be non-negative")

        if amount <= WITHHOLDING_TAX_THRESHOLD:
            tax = amount * WITHHOLDING_TAX_RATE_UP_TO_THRESHOLD
        else:
            tax = (
                WITHHOLDING_TAX_THRESHOLD * WITHHOLDING_TAX_RATE_UP_TO_THRESHOLD
                + (amount - WITHHOLDING_TAX_THRESHOLD) * WITHHOLDING_TAX_RATE_ABOVE_THRESHOLD
            )
        return tax.quantize(Decimal("1"), rounding=ROUND_DOWN)
