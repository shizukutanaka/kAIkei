"""高年齢雇用継続基本給付金の支給額計算(雇用保険法61条)。

60歳以上65歳未満・被保険者期間5年以上の被保険者で、支給対象月の賃金が
60歳到達時等の賃金月額(みなし賃金月額)の75%未満に低下した場合に支給される。

支給率(低下率 = 支給対象月の賃金 / みなし賃金月額):
  - 低下率 61%以下      : 支給額 = 支給対象月の賃金 × 15%
  - 61%超 75%未満       : 支給額 = 137.25/280 × みなし賃金月額 − 183/280 × 支給対象月の賃金
                          (低下率61%で15%、75%で0%となる逓減式)
  - 75%以上             : 不支給

調整:
  - みなし賃金月額には上限・下限がある(年度改定)。
  - 支給対象月の賃金 + 支給額 が支給限度額を超える場合、超過分を減額。
  - 支給額が最低限度額以下の場合は不支給。

上限・限度額・最低額は毎年8月に改定されるため、既定値は令和5年8月時点の
参考値とし、呼び出し側で年度値を指定できるようにしている。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# 令和5年8月1日〜の参考値(年度改定)。
WAGE_MONTH_CAP = Decimal("486300")  # みなし賃金月額の上限
WAGE_MONTH_FLOOR = Decimal("82380")  # みなし賃金月額の下限
SUPPLY_LIMIT = Decimal("370452")  # 支給限度額
MIN_BENEFIT = Decimal("2196")  # 最低限度額

RATIO_FLAT = Decimal("0.61")  # 61%以下は一律15%
RATIO_CEILING = Decimal("0.75")  # 75%以上は不支給
FLAT_RATE = Decimal("0.15")
DECLINE_RATE_WAGE_AT_60 = Decimal("137.25") / Decimal("280")
DECLINE_RATE_CURRENT = Decimal("183") / Decimal("280")

MIN_INSURED_MONTHS = 60  # 被保険者期間5年
AGE_LOWER = 60
AGE_UPPER = 65


@dataclass(frozen=True)
class HighAgeBenefitResult:
    eligible: bool
    reduction_ratio: Decimal
    benefit_amount: Decimal
    reason: str


class HighAgeEmploymentBenefitService:
    """高年齢雇用継続基本給付金の支給額を算定する純粋サービス。"""

    @classmethod
    def compute(
        cls,
        *,
        age: int,
        insured_months: int,
        wage_at_60: Decimal,
        current_wage: Decimal,
        wage_month_cap: Decimal = WAGE_MONTH_CAP,
        wage_month_floor: Decimal = WAGE_MONTH_FLOOR,
        supply_limit: Decimal = SUPPLY_LIMIT,
        min_benefit: Decimal = MIN_BENEFIT,
    ) -> HighAgeBenefitResult:
        if wage_at_60 <= 0:
            raise ValueError("wage_at_60 must be positive")
        if current_wage < 0:
            raise ValueError("current_wage must not be negative")

        if not (AGE_LOWER <= age < AGE_UPPER):
            return cls._ineligible(current_wage, wage_at_60, "60歳以上65歳未満ではない")
        if insured_months < MIN_INSURED_MONTHS:
            return cls._ineligible(current_wage, wage_at_60, "被保険者期間が5年未満")

        capped_wage_at_60 = min(max(wage_at_60, wage_month_floor), wage_month_cap)
        ratio = (current_wage / capped_wage_at_60).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)

        if ratio >= RATIO_CEILING:
            return cls._ineligible(current_wage, wage_at_60, "低下率が75%以上", reduction_ratio=ratio)
        if current_wage >= supply_limit:
            return cls._ineligible(
                current_wage, wage_at_60, "支給対象月の賃金が支給限度額以上", reduction_ratio=ratio
            )

        if ratio <= RATIO_FLAT:
            raw = current_wage * FLAT_RATE
        else:
            raw = DECLINE_RATE_WAGE_AT_60 * capped_wage_at_60 - DECLINE_RATE_CURRENT * current_wage

        benefit = raw.quantize(Decimal("1"), rounding=ROUND_DOWN)
        if benefit < 0:
            benefit = Decimal("0")

        # 支給対象月の賃金+支給額が支給限度額を超える場合は超過分を減額。
        if current_wage + benefit > supply_limit:
            benefit = supply_limit - current_wage

        if benefit <= min_benefit:
            return cls._ineligible(
                current_wage, wage_at_60, "支給額が最低限度額以下", reduction_ratio=ratio
            )

        return HighAgeBenefitResult(
            eligible=True,
            reduction_ratio=ratio,
            benefit_amount=benefit,
            reason="",
        )

    @classmethod
    def _ineligible(
        cls,
        current_wage: Decimal,
        wage_at_60: Decimal,
        reason: str,
        *,
        reduction_ratio: Decimal | None = None,
    ) -> HighAgeBenefitResult:
        ratio = reduction_ratio
        if ratio is None:
            ratio = (current_wage / wage_at_60).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
        return HighAgeBenefitResult(
            eligible=False,
            reduction_ratio=ratio,
            benefit_amount=Decimal("0"),
            reason=reason,
        )
