from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# 消費税法9条・9条の2 / 1,000万円基準
TAXABLE_ENTERPRISE_THRESHOLD = Decimal("10000000")


@dataclass(frozen=True)
class TaxableEnterpriseJudgmentResult:
    is_taxable: bool
    basis: str
    base_period_taxable_sales: Decimal
    specific_period_taxable_sales: Decimal
    specific_period_salaries: Decimal


class TaxableEnterpriseJudgmentService:
    @classmethod
    def judge(
        cls,
        base_period_taxable_sales: Decimal,
        specific_period_taxable_sales: Decimal,
        specific_period_salaries: Decimal,
    ) -> TaxableEnterpriseJudgmentResult:
        if base_period_taxable_sales < 0 or specific_period_taxable_sales < 0 or specific_period_salaries < 0:
            raise ValueError("inputs must be non-negative")

        if base_period_taxable_sales > TAXABLE_ENTERPRISE_THRESHOLD:
            return TaxableEnterpriseJudgmentResult(
                is_taxable=True,
                basis="base_period",
                base_period_taxable_sales=base_period_taxable_sales,
                specific_period_taxable_sales=specific_period_taxable_sales,
                specific_period_salaries=specific_period_salaries,
            )

        if (
            specific_period_taxable_sales > TAXABLE_ENTERPRISE_THRESHOLD
            and specific_period_salaries > TAXABLE_ENTERPRISE_THRESHOLD
        ):
            return TaxableEnterpriseJudgmentResult(
                is_taxable=True,
                basis="specific_period",
                base_period_taxable_sales=base_period_taxable_sales,
                specific_period_taxable_sales=specific_period_taxable_sales,
                specific_period_salaries=specific_period_salaries,
            )

        return TaxableEnterpriseJudgmentResult(
            is_taxable=False,
            basis="exempt",
            base_period_taxable_sales=base_period_taxable_sales,
            specific_period_taxable_sales=specific_period_taxable_sales,
            specific_period_salaries=specific_period_salaries,
        )
