from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_DOWN, Decimal

# 厚生年金保険料率 18.3%（全国一律・固定、厚生年金保険法）
PENSION_INSURANCE_RATE = Decimal("0.183")
# 健康保険料率 令和6年度の協会けんぽ東京の代表値。都道府県・年度ごとに必ず上書きする。
DEFAULT_HEALTH_INSURANCE_RATE = Decimal("0.0998")
# 介護保険料率 令和6年度の代表値。40〜64歳の第2号被保険者のみ適用、都道府県・年度ごとに上書きする。
DEFAULT_CARE_INSURANCE_RATE = Decimal("0.016")


@dataclass(frozen=True)
class SocialInsuranceBreakdown:
    total: Decimal
    employee: Decimal
    employer: Decimal


@dataclass(frozen=True)
class SocialInsuranceResult:
    standard_monthly_remuneration: Decimal
    health_rate: Decimal
    care_rate: Decimal
    care_applicable: bool
    health: SocialInsuranceBreakdown
    care: SocialInsuranceBreakdown
    pension: SocialInsuranceBreakdown
    total_employee: Decimal
    total_employer: Decimal
    total_premium: Decimal


class SocialInsurancePremiumService:
    @staticmethod
    def split_premium(total: Decimal) -> SocialInsuranceBreakdown:
        employee = (total / Decimal("2")).quantize(Decimal("1"), rounding=ROUND_HALF_DOWN)
        employer = total - employee
        return SocialInsuranceBreakdown(total=total, employee=employee, employer=employer)

    @classmethod
    def compute(
        cls,
        standard_monthly_remuneration: Decimal,
        health_rate: Decimal = DEFAULT_HEALTH_INSURANCE_RATE,
        care_rate: Decimal = DEFAULT_CARE_INSURANCE_RATE,
        care_applicable: bool = False,
    ) -> SocialInsuranceResult:
        if (
            standard_monthly_remuneration < 0
            or health_rate < 0
            or care_rate < 0
        ):
            raise ValueError("standard_monthly_remuneration and rates must be non-negative")

        health_total = standard_monthly_remuneration * health_rate
        care_total = standard_monthly_remuneration * care_rate if care_applicable else Decimal("0")
        pension_total = standard_monthly_remuneration * PENSION_INSURANCE_RATE

        health = cls.split_premium(health_total)
        care = cls.split_premium(care_total)
        pension = cls.split_premium(pension_total)

        total_employee = health.employee + care.employee + pension.employee
        total_employer = health.employer + care.employer + pension.employer
        total_premium = health.total + care.total + pension.total

        return SocialInsuranceResult(
            standard_monthly_remuneration=standard_monthly_remuneration,
            health_rate=health_rate,
            care_rate=care_rate,
            care_applicable=care_applicable,
            health=health,
            care=care,
            pension=pension,
            total_employee=total_employee,
            total_employer=total_employer,
            total_premium=total_premium,
        )

    @classmethod
    def compute_bonus(
        cls,
        health_standard_bonus: Decimal,
        pension_standard_bonus: Decimal,
        health_rate: Decimal = DEFAULT_HEALTH_INSURANCE_RATE,
        care_rate: Decimal = DEFAULT_CARE_INSURANCE_RATE,
        care_applicable: bool = False,
    ) -> SocialInsuranceResult:
        if (
            health_standard_bonus < 0
            or pension_standard_bonus < 0
            or health_rate < 0
            or care_rate < 0
        ):
            raise ValueError("standard bonuses and rates must be non-negative")

        health_total = health_standard_bonus * health_rate
        care_total = health_standard_bonus * care_rate if care_applicable else Decimal("0")
        pension_total = pension_standard_bonus * PENSION_INSURANCE_RATE

        health = cls.split_premium(health_total)
        care = cls.split_premium(care_total)
        pension = cls.split_premium(pension_total)

        total_employee = health.employee + care.employee + pension.employee
        total_employer = health.employer + care.employer + pension.employer
        total_premium = health.total + care.total + pension.total

        return SocialInsuranceResult(
            standard_monthly_remuneration=health_standard_bonus,
            health_rate=health_rate,
            care_rate=care_rate,
            care_applicable=care_applicable,
            health=health,
            care=care,
            pension=pension,
            total_employee=total_employee,
            total_employer=total_employer,
            total_premium=total_premium,
        )


# 介護保険の第2号被保険者は「40歳以上65歳未満」。年齢に達する日は誕生日の前日
# （年齢計算ニ関スル法律・民法143条）なので、1日生まれの人は前月から対象になる。
CARE_INSURANCE_START_AGE = 40
CARE_INSURANCE_END_AGE = 65


def _age_attained_on(birth_date: date, as_of: date) -> int:
    """`as_of` 時点の満年齢。

    満年齢に達するのは誕生日の前日なので、その分を前倒しして数える
    （例: 4月1日生まれは3月31日に加齢する）。
    """
    attained = as_of + timedelta(days=1)
    years = attained.year - birth_date.year
    if (attained.month, attained.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def care_insurance_applicable(birth_date: date | None, as_of: date) -> bool:
    """その月に介護保険料（第2号被保険者）を徴収するか。

    資格取得はその月から、喪失（65歳）はその月から対象外になるため、
    月末時点の満年齢で判定する。生年月日が不明なら徴収しない
    （誤って徴収するより、徴収漏れとして是正できる方を選ぶ）。
    """
    if birth_date is None:
        return False
    age = _age_attained_on(birth_date, as_of)
    return CARE_INSURANCE_START_AGE <= age < CARE_INSURANCE_END_AGE
