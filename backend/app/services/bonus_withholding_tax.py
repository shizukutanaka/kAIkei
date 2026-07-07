"""賞与の源泉徴収税額を算出する。

本モジュールでは、賞与に対する源泉徴収税額の算出率表そのものは埋め込まない。
実運用では「賞与に対する源泉徴収税額の算出率表」から、
前月の社会保険料等控除後給与と扶養親族等の数に応じた率を呼び出し側で取得し、
`bonus_tax_rate` として渡す前提とする。

ただし、次の2ケースでは率表方式を使わず月額表方式へ切り替える必要があるため、
本サービスで明示的に判定する。
1. 前月に給与の支払いがない。
2. 賞与額(社会保険料等控除後)が前月給与(社会保険料等控除後)の10倍を超える。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal


@dataclass(frozen=True)
class BonusWithholdingTaxResult:
    bonus_after_social_insurance: Decimal
    bonus_tax_rate: Decimal
    prior_month_salary_after_social_insurance: Decimal | None
    withholding_tax: Decimal | None
    requires_monthly_table: bool
    reason: str


class BonusWithholdingTaxService:
    @staticmethod
    def compute(
        bonus_after_social_insurance: Decimal,
        bonus_tax_rate: Decimal,
        prior_month_salary_after_social_insurance: Decimal | None = None,
    ) -> BonusWithholdingTaxResult:
        if bonus_after_social_insurance < 0:
            raise ValueError("bonus_after_social_insurance must be non-negative")
        if bonus_tax_rate < 0 or bonus_tax_rate > 1:
            raise ValueError("bonus_tax_rate must be between 0 and 1")
        if prior_month_salary_after_social_insurance is not None and prior_month_salary_after_social_insurance < 0:
            raise ValueError("prior_month_salary_after_social_insurance must be non-negative")

        if prior_month_salary_after_social_insurance is None:
            return BonusWithholdingTaxResult(
                bonus_after_social_insurance=bonus_after_social_insurance,
                bonus_tax_rate=bonus_tax_rate,
                prior_month_salary_after_social_insurance=None,
                withholding_tax=None,
                requires_monthly_table=True,
                reason="no_prior_month_salary",
            )

        if bonus_after_social_insurance > prior_month_salary_after_social_insurance * Decimal("10"):
            return BonusWithholdingTaxResult(
                bonus_after_social_insurance=bonus_after_social_insurance,
                bonus_tax_rate=bonus_tax_rate,
                prior_month_salary_after_social_insurance=prior_month_salary_after_social_insurance,
                withholding_tax=None,
                requires_monthly_table=True,
                reason="bonus_exceeds_10x_prior_salary",
            )

        withholding_tax = (bonus_after_social_insurance * bonus_tax_rate).quantize(Decimal("1"), rounding=ROUND_DOWN)
        return BonusWithholdingTaxResult(
            bonus_after_social_insurance=bonus_after_social_insurance,
            bonus_tax_rate=bonus_tax_rate,
            prior_month_salary_after_social_insurance=prior_month_salary_after_social_insurance,
            withholding_tax=withholding_tax,
            requires_monthly_table=False,
            reason="rate_table",
        )
