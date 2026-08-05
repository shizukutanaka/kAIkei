"""月次給与明細(差引支給額)の総合計算オーケストレーション。

各控除項目の個別計算は再実装せず、既存サービスを組み合わせる。
- 社会保険料(健保/介護/厚年): SocialInsurancePremiumService.compute(標準報酬月額ベース)
- 雇用保険料: LaborInsuranceService.calculate_employee_premium(賃金総額ベース)
- 源泉所得税(月額表 甲欄)・住民税(特別徴収)は月額表・通知額に依存するため入力として受け取る。

社会保険料は標準報酬月額(定時決定/随時改定で確定した額)に基づき算出し、当月の実支給額とは
切り離す。雇用保険料は当月の賃金総額(通勤手当を含む)に基づく。
差引支給額 = 総支給額 − 控除合計。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.labor_insurance import BUSINESS_TYPE_GENERAL, DEFAULT_WORKERS_COMPENSATION_RATE, LaborInsuranceService
from app.services.social_insurance import (
    DEFAULT_CARE_INSURANCE_RATE,
    DEFAULT_HEALTH_INSURANCE_RATE,
    SocialInsurancePremiumService,
    SocialInsuranceResult,
)


@dataclass(frozen=True)
class MonthlyPayslipResult:
    taxable_earnings: Decimal
    non_taxable_commute_allowance: Decimal
    total_earnings: Decimal
    social_insurance: SocialInsuranceResult
    social_insurance_employee: Decimal
    employment_insurance_employee: Decimal
    income_tax: Decimal
    residence_tax: Decimal
    other_deductions: Decimal
    total_deductions: Decimal
    net_pay: Decimal


class MonthlyPayslipService:
    @classmethod
    def compute(
        cls,
        base_salary: Decimal,
        standard_monthly_remuneration: Decimal,
        overtime_pay: Decimal = Decimal("0"),
        other_taxable_allowances: Decimal = Decimal("0"),
        non_taxable_commute_allowance: Decimal = Decimal("0"),
        income_tax: Decimal = Decimal("0"),
        residence_tax: Decimal = Decimal("0"),
        other_deductions: Decimal = Decimal("0"),
        business_type: str = BUSINESS_TYPE_GENERAL,
        health_rate: Decimal = DEFAULT_HEALTH_INSURANCE_RATE,
        care_rate: Decimal = DEFAULT_CARE_INSURANCE_RATE,
        care_applicable: bool = False,
        workers_comp_rate: Decimal = DEFAULT_WORKERS_COMPENSATION_RATE,
        employment_insurance_exempt: bool = False,
    ) -> MonthlyPayslipResult:
        amounts = {
            "base_salary": base_salary,
            "overtime_pay": overtime_pay,
            "other_taxable_allowances": other_taxable_allowances,
            "non_taxable_commute_allowance": non_taxable_commute_allowance,
            "income_tax": income_tax,
            "residence_tax": residence_tax,
            "other_deductions": other_deductions,
        }
        for name, value in amounts.items():
            if value < 0:
                raise ValueError(f"{name} must be non-negative")

        taxable_earnings = base_salary + overtime_pay + other_taxable_allowances
        total_earnings = taxable_earnings + non_taxable_commute_allowance

        social_insurance = SocialInsurancePremiumService.compute(
            standard_monthly_remuneration=standard_monthly_remuneration,
            health_rate=health_rate,
            care_rate=care_rate,
            care_applicable=care_applicable,
        )
        labor = LaborInsuranceService.calculate_employee_premium(
            gross_monthly_pay=total_earnings,
            business_type=business_type,
            is_exempt=employment_insurance_exempt,
            workers_comp_rate=workers_comp_rate,
        )

        total_deductions = (
            social_insurance.total_employee
            + labor.employment_insurance_employee
            + income_tax
            + residence_tax
            + other_deductions
        )
        net_pay = total_earnings - total_deductions

        return MonthlyPayslipResult(
            taxable_earnings=taxable_earnings,
            non_taxable_commute_allowance=non_taxable_commute_allowance,
            total_earnings=total_earnings,
            social_insurance=social_insurance,
            social_insurance_employee=social_insurance.total_employee,
            employment_insurance_employee=labor.employment_insurance_employee,
            income_tax=income_tax,
            residence_tax=residence_tax,
            other_deductions=other_deductions,
            total_deductions=total_deductions,
            net_pay=net_pay,
        )
