from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

BUSINESS_TYPE_GENERAL = "general"
BUSINESS_TYPE_AGRICULTURE_FORESTRY_FISHERY_SAKE = "agriculture_forestry_fishery_sake"
BUSINESS_TYPE_CONSTRUCTION = "construction"

EMPLOYMENT_INSURANCE_RATE_EMPLOYEE_GENERAL = Decimal("0.006")
EMPLOYMENT_INSURANCE_RATE_EMPLOYER_GENERAL = Decimal("0.0095")
EMPLOYMENT_INSURANCE_RATE_EMPLOYEE_AGRICULTURE = Decimal("0.007")
EMPLOYMENT_INSURANCE_RATE_EMPLOYER_AGRICULTURE = Decimal("0.0105")
EMPLOYMENT_INSURANCE_RATE_EMPLOYEE_CONSTRUCTION = Decimal("0.007")
EMPLOYMENT_INSURANCE_RATE_EMPLOYER_CONSTRUCTION = Decimal("0.0105")

# 労災保険の標準的な目安。実際の料率は業種等で変動するため、必要に応じて上書きする。
DEFAULT_WORKERS_COMPENSATION_RATE = Decimal("0.003")

BUSINESS_TYPE_RATES: dict[str, tuple[Decimal, Decimal]] = {
    BUSINESS_TYPE_GENERAL: (
        EMPLOYMENT_INSURANCE_RATE_EMPLOYEE_GENERAL,
        EMPLOYMENT_INSURANCE_RATE_EMPLOYER_GENERAL,
    ),
    BUSINESS_TYPE_AGRICULTURE_FORESTRY_FISHERY_SAKE: (
        EMPLOYMENT_INSURANCE_RATE_EMPLOYEE_AGRICULTURE,
        EMPLOYMENT_INSURANCE_RATE_EMPLOYER_AGRICULTURE,
    ),
    BUSINESS_TYPE_CONSTRUCTION: (
        EMPLOYMENT_INSURANCE_RATE_EMPLOYEE_CONSTRUCTION,
        EMPLOYMENT_INSURANCE_RATE_EMPLOYER_CONSTRUCTION,
    ),
}


@dataclass(frozen=True)
class LaborInsuranceBreakdown:
    employment_insurance_employee: Decimal
    employment_insurance_employer: Decimal
    workers_comp_employer: Decimal
    total_employee: Decimal
    total_employer: Decimal
    total_premium: Decimal


@dataclass(frozen=True)
class LaborInsuranceCompanySummary:
    employee_count: int
    total_employee_premium: Decimal
    total_employer_premium: Decimal
    total_premium: Decimal
    items: list[LaborInsuranceBreakdown]


class LaborInsuranceService:
    @staticmethod
    def _round_yen(value: Decimal) -> Decimal:
        return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _employment_rates(business_type: str) -> tuple[Decimal, Decimal]:
        try:
            return BUSINESS_TYPE_RATES[business_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported business_type: {business_type}") from exc

    @staticmethod
    def calculate_employee_premium(
        *,
        gross_monthly_pay: Decimal,
        business_type: str,
        age: int | None = None,
        is_exempt: bool = False,
        workers_comp_rate: Decimal = DEFAULT_WORKERS_COMPENSATION_RATE,
    ) -> LaborInsuranceBreakdown:
        employee_rate, employer_rate = LaborInsuranceService._employment_rates(business_type)
        exempt = is_exempt or (age is not None and age >= 65)

        if gross_monthly_pay <= 0 or exempt:
            employment_employee = Decimal("0")
            employment_employer = Decimal("0")
        else:
            employment_employee = LaborInsuranceService._round_yen(gross_monthly_pay * employee_rate)
            employment_employer = LaborInsuranceService._round_yen(gross_monthly_pay * employer_rate)

        workers_comp_employer = LaborInsuranceService._round_yen(gross_monthly_pay * workers_comp_rate)
        total_employee = employment_employee
        total_employer = employment_employer + workers_comp_employer
        total_premium = total_employee + total_employer

        return LaborInsuranceBreakdown(
            employment_insurance_employee=employment_employee,
            employment_insurance_employer=employment_employer,
            workers_comp_employer=workers_comp_employer,
            total_employee=total_employee,
            total_employer=total_employer,
            total_premium=total_premium,
        )

    @staticmethod
    def summarize_company_premiums(items: list[LaborInsuranceBreakdown]) -> LaborInsuranceCompanySummary:
        total_employee = sum((item.total_employee for item in items), Decimal("0"))
        total_employer = sum((item.total_employer for item in items), Decimal("0"))
        total_premium = total_employee + total_employer
        return LaborInsuranceCompanySummary(
            employee_count=len(items),
            total_employee_premium=total_employee,
            total_employer_premium=total_employer,
            total_premium=total_premium,
            items=items,
        )
