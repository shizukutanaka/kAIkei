"""出生時育児休業給付金(産後パパ育休)の支給額計算(雇用保険法61条の8)。

子の出生後8週間以内に4週間(28日)まで取得できる「出生時育児休業(産後パパ育休)」
に対して支給される。通常の育児休業給付金とは別枠で、休業開始前2年間にみなし
被保険者期間が12か月以上ある場合に支給される。

支給額:
    支給額 = 休業開始時賃金日額 × 支給日数 × 67%

支給日数:
    通算28日を上限とする(1回の休業でも分割でも合計28日まで)。

休業開始時賃金日額:
    休業開始前6か月の賃金総額 ÷ 180。上限・下限あり(年度改定)。

休業中に就業して賃金が支払われた場合の調整(賃金月額 = 賃金日額 × 支給日数):
    - 賃金月額の80%以上         : 不支給
    - 賃金月額の13%以下         : 全額支給
    - その間                    : 賃金月額×80% − 支払賃金 を支給

賃金日額の上限・下限は毎年8月に改定されるため、既定値は令和6年8月時点の参考値とし、
呼び出し側で年度値を指定できるようにしている。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# 令和6年8月1日〜の参考値(年度改定)。育児休業給付金と共通。
DAILY_WAGE_CAP = Decimal("15430")
DAILY_WAGE_FLOOR = Decimal("2869")

RATE = Decimal("0.67")
MAX_LEAVE_DAYS = 28  # 産後パパ育休の支給日数上限(通算)

REDUCTION_FLOOR = Decimal("0.13")  # この割合以下の賃金支払なら全額支給
NO_PAYMENT_RATIO = Decimal("0.80")  # 賃金月額の80%以上支払で不支給

MIN_INSURED_MONTHS = 12
WAGE_BASE_DAYS = Decimal("180")


@dataclass(frozen=True)
class PostnatalLeaveBenefitResult:
    eligible: bool
    daily_wage: Decimal
    payable_days: int
    benefit_amount: Decimal
    reason: str


class PostnatalLeaveBenefitService:
    """出生時育児休業給付金の支給額を算定する純粋サービス。"""

    @classmethod
    def compute(
        cls,
        *,
        wage_total_6m: Decimal,
        insured_months: int,
        leave_days: int,
        cumulative_days_before: int = 0,
        wage_paid_during_leave: Decimal = Decimal("0"),
        daily_wage_cap: Decimal = DAILY_WAGE_CAP,
        daily_wage_floor: Decimal = DAILY_WAGE_FLOOR,
    ) -> PostnatalLeaveBenefitResult:
        if wage_total_6m <= 0:
            raise ValueError("wage_total_6m must be positive")
        if leave_days <= 0:
            raise ValueError("leave_days must be positive")
        if cumulative_days_before < 0:
            raise ValueError("cumulative_days_before must not be negative")
        if wage_paid_during_leave < 0:
            raise ValueError("wage_paid_during_leave must not be negative")

        if insured_months < MIN_INSURED_MONTHS:
            return cls._ineligible("みなし被保険者期間が12か月未満")

        remaining_days = MAX_LEAVE_DAYS - cumulative_days_before
        if remaining_days <= 0:
            return cls._ineligible("出生時育児休業給付の通算28日を超過")
        payable_days = min(leave_days, remaining_days)

        daily_wage = (wage_total_6m / WAGE_BASE_DAYS).quantize(
            Decimal("1"), rounding=ROUND_DOWN
        )
        daily_wage = min(max(daily_wage, daily_wage_floor), daily_wage_cap)

        wage_base = daily_wage * Decimal(payable_days)

        if wage_paid_during_leave >= wage_base * NO_PAYMENT_RATIO:
            return cls._ineligible(
                "休業期間中の賃金が賃金月額の80%以上",
                daily_wage=daily_wage,
                payable_days=payable_days,
            )

        gross = (wage_base * RATE).quantize(Decimal("1"), rounding=ROUND_DOWN)

        if wage_paid_during_leave > wage_base * REDUCTION_FLOOR:
            adjusted = (wage_base * NO_PAYMENT_RATIO - wage_paid_during_leave).quantize(
                Decimal("1"), rounding=ROUND_DOWN
            )
            benefit = min(gross, max(adjusted, Decimal("0")))
        else:
            benefit = gross

        if benefit <= 0:
            return cls._ineligible(
                "調整後の支給額が0以下",
                daily_wage=daily_wage,
                payable_days=payable_days,
            )

        return PostnatalLeaveBenefitResult(
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
        payable_days: int = 0,
    ) -> PostnatalLeaveBenefitResult:
        return PostnatalLeaveBenefitResult(
            eligible=False,
            daily_wage=daily_wage,
            payable_days=payable_days,
            benefit_amount=Decimal("0"),
            reason=reason,
        )
