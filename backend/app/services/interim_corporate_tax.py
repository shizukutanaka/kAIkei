from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# 法人税法71条 / 予定申告（前期実績基準）
INTERIM_CORPORATE_TAX_SIX_MONTH_FACTOR = Decimal("6")
INTERIM_CORPORATE_TAX_ROUNDING_UNIT = Decimal("100")
INTERIM_CORPORATE_TAX_FILING_THRESHOLD = Decimal("100000")


@dataclass(frozen=True)
class InterimCorporateTaxResult:
    interim_tax: Decimal
    filing_required: bool
    prior_period_months: int


class InterimCorporateTaxService:
    @staticmethod
    def _floor_to_100(amount: Decimal) -> Decimal:
        return (amount // INTERIM_CORPORATE_TAX_ROUNDING_UNIT) * INTERIM_CORPORATE_TAX_ROUNDING_UNIT

    @classmethod
    def compute(cls, prior_year_corporate_tax: Decimal, prior_period_months: int = 12) -> InterimCorporateTaxResult:
        if prior_year_corporate_tax < 0:
            raise ValueError("prior_year_corporate_tax must be non-negative")
        if prior_period_months < 1 or prior_period_months > 12:
            raise ValueError("prior_period_months must be between 1 and 12")

        interim_tax = cls._floor_to_100(
            prior_year_corporate_tax * INTERIM_CORPORATE_TAX_SIX_MONTH_FACTOR / Decimal(prior_period_months)
        )
        filing_required = interim_tax > INTERIM_CORPORATE_TAX_FILING_THRESHOLD
        return InterimCorporateTaxResult(
            interim_tax=interim_tax,
            filing_required=filing_required,
            prior_period_months=prior_period_months,
        )
