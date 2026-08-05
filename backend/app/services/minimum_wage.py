"""最低賃金の充足チェック。

最低賃金法4条: 使用者は地域別最低賃金額(時間額)以上の賃金を支払わなければならない。
月給制等の場合は所定労働時間で時間額に換算して比較する。最低賃金の対象となる賃金には
通勤手当・家族手当・精皆勤手当・時間外割増賃金・賞与等は算入しないため、呼び出し側で
それらを除いた「最低賃金の対象賃金」を渡す前提とする。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

WAGE_TYPE_HOURLY = "hourly"
WAGE_TYPE_MONTHLY = "monthly"


@dataclass(frozen=True)
class MinimumWageResult:
    effective_hourly_wage: Decimal
    minimum_hourly_wage: Decimal
    meets_minimum: bool
    shortfall_per_hour: Decimal


class MinimumWageService:
    @classmethod
    def check(
        cls,
        minimum_hourly_wage: Decimal,
        wage_type: str,
        hourly_wage: Decimal | None = None,
        monthly_wage: Decimal | None = None,
        monthly_scheduled_hours: Decimal | None = None,
    ) -> MinimumWageResult:
        if minimum_hourly_wage < 0:
            raise ValueError("minimum_hourly_wage must be non-negative")

        if wage_type == WAGE_TYPE_HOURLY:
            if hourly_wage is None:
                raise ValueError("hourly_wage is required for hourly wage_type")
            if hourly_wage < 0:
                raise ValueError("hourly_wage must be non-negative")
            effective = hourly_wage
        elif wage_type == WAGE_TYPE_MONTHLY:
            if monthly_wage is None or monthly_scheduled_hours is None:
                raise ValueError("monthly_wage and monthly_scheduled_hours are required for monthly wage_type")
            if monthly_wage < 0:
                raise ValueError("monthly_wage must be non-negative")
            if monthly_scheduled_hours <= 0:
                raise ValueError("monthly_scheduled_hours must be positive")
            effective = (monthly_wage / monthly_scheduled_hours).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            raise ValueError(f"unsupported wage_type: {wage_type}")

        meets_minimum = effective >= minimum_hourly_wage
        shortfall = Decimal("0") if meets_minimum else minimum_hourly_wage - effective
        return MinimumWageResult(
            effective_hourly_wage=effective,
            minimum_hourly_wage=minimum_hourly_wage,
            meets_minimum=meets_minimum,
            shortfall_per_hour=shortfall,
        )
