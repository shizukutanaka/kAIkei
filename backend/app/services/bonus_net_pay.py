"""賞与の差引支給額(手取り)を組み立てるオーケストレーション。

本モジュールは、賞与の手取り計算を構成する各税・保険料の個別計算を再実装しない。
以下の既存サービスを組み合わせるだけに徹する。
- 社会保険料: SocialInsurancePremiumService.compute_bonus
- 雇用保険料: BonusEmploymentInsuranceService.compute
- 源泉所得税: BonusWithholdingTaxService.compute

標準賞与額の算定は、健康保険法・厚生年金保険法の上限だけを本サービスで持ち、
千円未満切捨は既存の floor-to-1000 ヘルパーを利用する。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.bonus_employment_insurance import BonusEmploymentInsuranceResult, BonusEmploymentInsuranceService
from app.services.bonus_withholding_tax import BonusWithholdingTaxService
from app.services.labor_insurance import BUSINESS_TYPE_GENERAL
from app.services.labor_insurance_annual import LaborInsuranceAnnualUpdateService
from app.services.social_insurance import (
    DEFAULT_CARE_INSURANCE_RATE,
    DEFAULT_HEALTH_INSURANCE_RATE,
    SocialInsurancePremiumService,
    SocialInsuranceResult,
)

# 健康保険 標準賞与額の年度累計上限 5,730,000円（4/1〜翌3/31）
HEALTH_STANDARD_BONUS_FISCAL_YEAR_CAP = Decimal("5730000")
# 厚生年金保険 標準賞与額の1回あたり上限 1,500,000円
PENSION_STANDARD_BONUS_PER_PAYMENT_CAP = Decimal("1500000")


@dataclass(frozen=True)
class BonusNetPayResult:
    gross_bonus: Decimal
    standard_bonus: Decimal
    health_standard_bonus: Decimal
    pension_standard_bonus: Decimal
    social_insurance: SocialInsuranceResult
    employment_insurance: BonusEmploymentInsuranceResult
    employment_insurance_employee: Decimal
    bonus_after_social_insurance: Decimal
    withholding_tax: Decimal | None
    requires_monthly_table: bool
    reason: str
    total_employee_deductions: Decimal
    net_pay: Decimal | None


class BonusNetPayService:
    @classmethod
    def compute(
        cls,
        gross_bonus: Decimal,
        business_type: str = BUSINESS_TYPE_GENERAL,
        health_rate: Decimal = DEFAULT_HEALTH_INSURANCE_RATE,
        care_rate: Decimal = DEFAULT_CARE_INSURANCE_RATE,
        care_applicable: bool = False,
        bonus_tax_rate: Decimal | None = None,
        prior_month_salary_after_social_insurance: Decimal | None = None,
        cumulative_health_standard_bonus_ytd: Decimal = Decimal("0"),
    ) -> BonusNetPayResult:
        if gross_bonus < 0:
            raise ValueError("gross_bonus must be non-negative")
        if cumulative_health_standard_bonus_ytd < 0:
            raise ValueError("cumulative_health_standard_bonus_ytd must be non-negative")
        if bonus_tax_rate is None:
            raise ValueError("bonus_tax_rate must be provided")

        standard_bonus = LaborInsuranceAnnualUpdateService.floor_to_1000(gross_bonus)
        health_remaining = HEALTH_STANDARD_BONUS_FISCAL_YEAR_CAP - cumulative_health_standard_bonus_ytd
        if health_remaining < 0:
            health_remaining = Decimal("0")
        health_standard_bonus = standard_bonus if standard_bonus <= health_remaining else health_remaining
        pension_standard_bonus = (
            standard_bonus
            if standard_bonus <= PENSION_STANDARD_BONUS_PER_PAYMENT_CAP
            else PENSION_STANDARD_BONUS_PER_PAYMENT_CAP
        )

        social_insurance = SocialInsurancePremiumService.compute_bonus(
            health_standard_bonus=health_standard_bonus,
            pension_standard_bonus=pension_standard_bonus,
            health_rate=health_rate,
            care_rate=care_rate,
            care_applicable=care_applicable,
        )
        employment_insurance = BonusEmploymentInsuranceService.compute(
            bonus_amount=gross_bonus,
            business_type=business_type,
        )
        bonus_after_social_insurance = gross_bonus - social_insurance.total_employee - employment_insurance.employee_premium
        withholding = BonusWithholdingTaxService.compute(
            bonus_after_social_insurance=bonus_after_social_insurance,
            bonus_tax_rate=bonus_tax_rate,
            prior_month_salary_after_social_insurance=prior_month_salary_after_social_insurance,
        )

        total_employee_deductions = social_insurance.total_employee + employment_insurance.employee_premium
        if withholding.requires_monthly_table:
            net_pay = None
        else:
            net_pay = gross_bonus - total_employee_deductions - withholding.withholding_tax

        return BonusNetPayResult(
            gross_bonus=gross_bonus,
            standard_bonus=standard_bonus,
            health_standard_bonus=health_standard_bonus,
            pension_standard_bonus=pension_standard_bonus,
            social_insurance=social_insurance,
            employment_insurance=employment_insurance,
            employment_insurance_employee=employment_insurance.employee_premium,
            bonus_after_social_insurance=bonus_after_social_insurance,
            withholding_tax=withholding.withholding_tax,
            requires_monthly_table=withholding.requires_monthly_table,
            reason=withholding.reason,
            total_employee_deductions=total_employee_deductions,
            net_pay=net_pay,
        )
