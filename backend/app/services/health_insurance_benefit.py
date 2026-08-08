"""健康保険の傷病手当金・出産手当金の支給額計算(健保法99条・102条)。

支給日額:
  支給開始日以前の継続した12か月間の各月の標準報酬月額の平均額 ÷ 30 × 2/3
  - ÷30の額は10円未満を四捨五入
  - ×2/3の額は1円未満を四捨五入
  - 被保険者期間が12か月未満の場合は、当該期間の標準報酬月額平均額と、全被保険者
    の標準報酬月額の平均額(協会けんぽが定める額・年度改定)のいずれか低い方を使う

傷病手当金:
  - 連続3日の待期完成後、4日目以降の労務不能日に支給
  - 支給開始日から通算1年6か月まで(2022年改正で通算化)
  - 報酬が支払われた場合は日額との差額を支給

出産手当金:
  - 出産日以前42日(多胎98日)から出産後56日までの範囲で労務に服さなかった日に支給
  - 報酬が支払われた場合は日額との差額を支給
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

INJURY_WAITING_DAYS = 3
MATERNITY_BEFORE_LIMIT_SINGLE = 42
MATERNITY_BEFORE_LIMIT_MULTIPLE = 98
MATERNITY_AFTER_LIMIT = 56

# 全被保険者の標準報酬月額の平均額(協会けんぽ・年度改定の参考値)。
DEFAULT_STANDARD_AVERAGE = Decimal("300000")


@dataclass(frozen=True)
class DailyBenefit:
    daily_base: Decimal
    daily_benefit: Decimal


@dataclass(frozen=True)
class BenefitResult:
    daily_benefit: Decimal
    effective_daily_benefit: Decimal
    payable_days: int
    total_amount: Decimal


class HealthInsuranceBenefitService:
    """傷病手当金・出産手当金の支給額を算定する純粋サービス。"""

    @classmethod
    def daily_benefit(
        cls,
        *,
        avg_standard_monthly: Decimal,
        insured_months: int,
        standard_average: Decimal = DEFAULT_STANDARD_AVERAGE,
    ) -> DailyBenefit:
        if avg_standard_monthly <= 0:
            raise ValueError("avg_standard_monthly must be positive")
        if insured_months < 0:
            raise ValueError("insured_months must not be negative")

        base_monthly = avg_standard_monthly
        if insured_months < 12:
            base_monthly = min(avg_standard_monthly, standard_average)

        # ÷30 は10円未満四捨五入。
        daily_base = (base_monthly / Decimal("30") / Decimal("10")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        ) * Decimal("10")
        # ×2/3 は1円未満四捨五入。
        daily = (daily_base * Decimal("2") / Decimal("3")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        return DailyBenefit(daily_base=daily_base, daily_benefit=daily)

    @classmethod
    def injury_allowance(
        cls,
        *,
        avg_standard_monthly: Decimal,
        insured_months: int,
        absent_days: int,
        waiting_completed: bool = False,
        daily_remuneration: Decimal = Decimal("0"),
        standard_average: Decimal = DEFAULT_STANDARD_AVERAGE,
    ) -> BenefitResult:
        if absent_days < 0:
            raise ValueError("absent_days must not be negative")
        if daily_remuneration < 0:
            raise ValueError("daily_remuneration must not be negative")

        daily = cls.daily_benefit(
            avg_standard_monthly=avg_standard_monthly,
            insured_months=insured_months,
            standard_average=standard_average,
        ).daily_benefit

        payable_days = absent_days if waiting_completed else max(absent_days - INJURY_WAITING_DAYS, 0)

        return cls._build_result(daily, daily_remuneration, payable_days)

    @classmethod
    def maternity_allowance(
        cls,
        *,
        avg_standard_monthly: Decimal,
        insured_months: int,
        days_before_birth: int,
        days_after_birth: int,
        multiple_pregnancy: bool = False,
        daily_remuneration: Decimal = Decimal("0"),
        standard_average: Decimal = DEFAULT_STANDARD_AVERAGE,
    ) -> BenefitResult:
        if days_before_birth < 0 or days_after_birth < 0:
            raise ValueError("days must not be negative")
        if daily_remuneration < 0:
            raise ValueError("daily_remuneration must not be negative")

        daily = cls.daily_benefit(
            avg_standard_monthly=avg_standard_monthly,
            insured_months=insured_months,
            standard_average=standard_average,
        ).daily_benefit

        before_limit = (
            MATERNITY_BEFORE_LIMIT_MULTIPLE if multiple_pregnancy else MATERNITY_BEFORE_LIMIT_SINGLE
        )
        payable_days = min(days_before_birth, before_limit) + min(days_after_birth, MATERNITY_AFTER_LIMIT)

        return cls._build_result(daily, daily_remuneration, payable_days)

    @classmethod
    def _build_result(
        cls, daily: Decimal, daily_remuneration: Decimal, payable_days: int
    ) -> BenefitResult:
        effective = daily - daily_remuneration
        if effective < 0:
            effective = Decimal("0")
        total = effective * payable_days
        return BenefitResult(
            daily_benefit=daily,
            effective_daily_benefit=effective,
            payable_days=payable_days,
            total_amount=total,
        )
