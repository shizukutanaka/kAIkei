"""育児休業給付金の支給額計算(雇用保険法61条の7)。

雇用保険の被保険者が1歳(一定の場合1歳6か月・2歳)未満の子を養育するため
育児休業を取得し、休業開始前2年間にみなし被保険者期間が12か月以上ある場合に
支給される。

支給額(1支給単位期間・原則30日):
  支給額 = 休業開始時賃金日額 × 支給日数 × 給付率

給付率:
  - 育児休業開始から通算180日目まで : 67%(67/100)
  - 181日目以降                     : 50%(50/100)

休業開始時賃金日額:
  - 休業開始前6か月の賃金総額 ÷ 180
  - 賃金日額には上限・下限がある(年度改定)。

支給単位期間中に賃金が支払われた場合の調整:
  - 休業開始時賃金月額(賃金日額×支給日数)の80%以上 : 不支給
  - 給付率に応じた下限割合(67%期間13%・50%期間30%)以下 : 全額支給
  - その間                                             : 賃金月額×80% − 支払賃金 を支給

支給限度額(賃金月額換算)は給付率ごとに定められ毎年8月に改定されるため、
既定値は令和6年8月時点の参考値とし、呼び出し側で年度値を指定できるようにしている。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# 令和6年8月1日〜の参考値(年度改定)。
DAILY_WAGE_CAP = Decimal("15430")  # 休業開始時賃金日額の上限
DAILY_WAGE_FLOOR = Decimal("2869")  # 休業開始時賃金日額の下限
SUPPLY_LIMIT_HIGH = Decimal("310143")  # 給付率67%時の支給限度額(30日換算)
SUPPLY_LIMIT_LOW = Decimal("231450")  # 給付率50%時の支給限度額(30日換算)

RATE_HIGH = Decimal("0.67")
RATE_LOW = Decimal("0.50")
RATE_SWITCH_DAYS = 180  # 通算180日目まで67%、以降50%

# 就業調整の下限割合(この割合以下の賃金支払なら全額支給)。
REDUCTION_FLOOR_HIGH = Decimal("0.13")
REDUCTION_FLOOR_LOW = Decimal("0.30")
NO_PAYMENT_RATIO = Decimal("0.80")  # 賃金月額の80%以上支払で不支給

MIN_INSURED_MONTHS = 12  # みなし被保険者期間12か月

WAGE_BASE_DAYS = Decimal("180")  # 賃金日額の算定基礎日数(6か月)


@dataclass(frozen=True)
class ChildcareLeaveBenefitResult:
    eligible: bool
    daily_wage: Decimal
    benefit_rate: Decimal
    benefit_amount: Decimal
    reason: str


class ChildcareLeaveBenefitService:
    """育児休業給付金の支給額を算定する純粋サービス。"""

    @classmethod
    def compute(
        cls,
        *,
        wage_total_6m: Decimal,
        insured_months: int,
        payment_days: int = 30,
        cumulative_days_before: int = 0,
        wage_paid_during_leave: Decimal = Decimal("0"),
        daily_wage_cap: Decimal = DAILY_WAGE_CAP,
        daily_wage_floor: Decimal = DAILY_WAGE_FLOOR,
        supply_limit_high: Decimal = SUPPLY_LIMIT_HIGH,
        supply_limit_low: Decimal = SUPPLY_LIMIT_LOW,
    ) -> ChildcareLeaveBenefitResult:
        if wage_total_6m <= 0:
            raise ValueError("wage_total_6m must be positive")
        if payment_days <= 0:
            raise ValueError("payment_days must be positive")
        if cumulative_days_before < 0:
            raise ValueError("cumulative_days_before must not be negative")
        if wage_paid_during_leave < 0:
            raise ValueError("wage_paid_during_leave must not be negative")

        if insured_months < MIN_INSURED_MONTHS:
            return cls._ineligible("みなし被保険者期間が12か月未満")

        daily_wage = (wage_total_6m / WAGE_BASE_DAYS).quantize(
            Decimal("1"), rounding=ROUND_DOWN
        )
        daily_wage = min(max(daily_wage, daily_wage_floor), daily_wage_cap)

        if cumulative_days_before >= RATE_SWITCH_DAYS:
            rate = RATE_LOW
            supply_limit = supply_limit_low
            reduction_floor = REDUCTION_FLOOR_LOW
        else:
            rate = RATE_HIGH
            supply_limit = supply_limit_high
            reduction_floor = REDUCTION_FLOOR_HIGH

        wage_monthly = daily_wage * Decimal(payment_days)

        # 就業調整: 支払賃金が賃金月額の80%以上なら不支給。
        if wage_paid_during_leave >= wage_monthly * NO_PAYMENT_RATIO:
            return cls._ineligible(
                "支給単位期間中の賃金が休業開始時賃金月額の80%以上",
                daily_wage=daily_wage,
                rate=rate,
            )

        gross = (wage_monthly * rate).quantize(Decimal("1"), rounding=ROUND_DOWN)
        if gross > supply_limit:
            gross = supply_limit

        # 賃金支払が下限割合を超え80%未満の場合は 賃金月額×80% − 支払賃金 に調整。
        if wage_paid_during_leave > wage_monthly * reduction_floor:
            adjusted = (wage_monthly * NO_PAYMENT_RATIO - wage_paid_during_leave).quantize(
                Decimal("1"), rounding=ROUND_DOWN
            )
            benefit = min(gross, max(adjusted, Decimal("0")))
        else:
            benefit = gross

        if benefit <= 0:
            return cls._ineligible(
                "調整後の支給額が0以下", daily_wage=daily_wage, rate=rate
            )

        return ChildcareLeaveBenefitResult(
            eligible=True,
            daily_wage=daily_wage,
            benefit_rate=rate,
            benefit_amount=benefit,
            reason="",
        )

    @classmethod
    def _ineligible(
        cls,
        reason: str,
        *,
        daily_wage: Decimal = Decimal("0"),
        rate: Decimal = Decimal("0"),
    ) -> ChildcareLeaveBenefitResult:
        return ChildcareLeaveBenefitResult(
            eligible=False,
            daily_wage=daily_wage,
            benefit_rate=rate,
            benefit_amount=Decimal("0"),
            reason=reason,
        )
