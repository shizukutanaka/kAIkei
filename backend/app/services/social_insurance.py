from __future__ import annotations

from dataclasses import dataclass
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
    def _split_premium(total: Decimal) -> SocialInsuranceBreakdown:
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

        health = cls._split_premium(health_total)
        care = cls._split_premium(care_total)
        pension = cls._split_premium(pension_total)

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
