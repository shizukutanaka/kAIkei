from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_DOWN, Decimal

from app.services.labor_insurance import LaborInsuranceService


@dataclass(frozen=True)
class BonusEmploymentInsuranceResult:
    employee_premium: Decimal
    employer_premium: Decimal
    total_premium: Decimal
    employee_rate: Decimal
    employer_rate: Decimal


class BonusEmploymentInsuranceService:
    @staticmethod
    def _round_yen(value: Decimal) -> Decimal:
        return value.quantize(Decimal("1"), rounding=ROUND_HALF_DOWN)

    @classmethod
    def compute(
        cls,
        bonus_amount: Decimal,
        business_type: str,
    ) -> BonusEmploymentInsuranceResult:
        if bonus_amount < 0:
            raise ValueError("bonus_amount must be non-negative")

        employee_rate, employer_rate = LaborInsuranceService._employment_rates(business_type)
        employee_premium = cls._round_yen(bonus_amount * employee_rate)
        employer_premium = cls._round_yen(bonus_amount * employer_rate)
        total_premium = employee_premium + employer_premium

        return BonusEmploymentInsuranceResult(
            employee_premium=employee_premium,
            employer_premium=employer_premium,
            total_premium=total_premium,
            employee_rate=employee_rate,
            employer_rate=employer_rate,
        )
