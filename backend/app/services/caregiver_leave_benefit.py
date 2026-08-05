"""介護休業給付金の支給額計算(雇用保険法61条の4)。

対象家族を介護するために介護休業を取得した雇用保険の被保険者で、休業開始前
2年間にみなし被保険者期間が12か月以上ある場合に支給される。

支給額(1支給単位期間・原則30日、最後の単位期間は暦日数):
  支給額 = 休業開始時賃金日額 × 支給日数 × 67%

休業開始時賃金日額:
  - 休業開始前6か月の賃金総額 ÷ 180
  - 休業開始時賃金月額(賃金日額×30)には上限・下限がある(年度改定)。

支給日数の通算:
  - 同一対象家族につき通算93日(3回まで分割可)が上限。

支給単位期間中に賃金が支払われた場合の調整:
  - 休業開始時賃金月額の80%以上       : 不支給
  - 休業開始時賃金月額の13%以下       : 全額支給
  - 13%超80%未満                     : 賃金月額×80% − 支払賃金 を支給

上限額・下限額・支給上限額は毎年8月1日に改定されるため、既定値は令和6年8月1日
時点の参考値(賃金月額上限518,100円・下限86,070円を30で除した日額換算、支給
上限額347,127円)とし、呼び出し側で年度値を指定できるようにしている。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# 令和6年8月1日〜の参考値(年度改定)。賃金日額の上限/下限は賃金月額限度額÷30。
DAILY_WAGE_CAP = Decimal("17270")  # 518,100 ÷ 30
DAILY_WAGE_FLOOR = Decimal("2869")  # 86,070 ÷ 30
SUPPLY_LIMIT = Decimal("347127")  # 支給上限額(30日換算)

RATE = Decimal("0.67")
REDUCTION_FLOOR = Decimal("0.13")  # この割合以下の賃金支払なら全額支給
NO_PAYMENT_RATIO = Decimal("0.80")  # 賃金月額の80%以上支払で不支給

MAX_TOTAL_DAYS = 93  # 同一対象家族につき通算93日
MIN_INSURED_MONTHS = 12  # みなし被保険者期間12か月

WAGE_BASE_DAYS = Decimal("180")  # 賃金日額の算定基礎日数(6か月)


@dataclass(frozen=True)
class CaregiverLeaveBenefitResult:
    eligible: bool
    daily_wage: Decimal
    payable_days: int
    benefit_amount: Decimal
    reason: str


class CaregiverLeaveBenefitService:
    """介護休業給付金の支給額を算定する純粋サービス。"""

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
        supply_limit: Decimal = SUPPLY_LIMIT,
    ) -> CaregiverLeaveBenefitResult:
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

        remaining_days = MAX_TOTAL_DAYS - cumulative_days_before
        if remaining_days <= 0:
            return cls._ineligible("介護休業給付の通算93日を超過")
        payable_days = min(payment_days, remaining_days)

        daily_wage = (wage_total_6m / WAGE_BASE_DAYS).quantize(
            Decimal("1"), rounding=ROUND_DOWN
        )
        daily_wage = min(max(daily_wage, daily_wage_floor), daily_wage_cap)

        wage_monthly = daily_wage * Decimal(payable_days)

        if wage_paid_during_leave >= wage_monthly * NO_PAYMENT_RATIO:
            return cls._ineligible(
                "支給単位期間中の賃金が休業開始時賃金月額の80%以上",
                daily_wage=daily_wage,
            )

        gross = (wage_monthly * RATE).quantize(Decimal("1"), rounding=ROUND_DOWN)
        if gross > supply_limit:
            gross = supply_limit

        if wage_paid_during_leave > wage_monthly * REDUCTION_FLOOR:
            adjusted = (wage_monthly * NO_PAYMENT_RATIO - wage_paid_during_leave).quantize(
                Decimal("1"), rounding=ROUND_DOWN
            )
            benefit = min(gross, max(adjusted, Decimal("0")))
        else:
            benefit = gross

        if benefit <= 0:
            return cls._ineligible("調整後の支給額が0以下", daily_wage=daily_wage)

        return CaregiverLeaveBenefitResult(
            eligible=True,
            daily_wage=daily_wage,
            payable_days=payable_days,
            benefit_amount=benefit,
            reason="",
        )

    @classmethod
    def _ineligible(
        cls,
        reason: str,
        *,
        daily_wage: Decimal = Decimal("0"),
    ) -> CaregiverLeaveBenefitResult:
        return CaregiverLeaveBenefitResult(
            eligible=False,
            daily_wage=daily_wage,
            payable_days=0,
            benefit_amount=Decimal("0"),
            reason=reason,
        )
