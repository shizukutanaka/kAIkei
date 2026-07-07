"""賞与支払届の電子申請連携用データ生成。

This CSV is a structured 連携用データ following 賞与支払届 記載事項.
It is NOT byte-verified against a specific e-Gov CSV仕様書 version and should
be mapped to the exact e-Gov 社会保険手続CSV layout at integration time.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import StringIO

from app.services.labor_insurance_annual import LaborInsuranceAnnualUpdateService

# 健康保険の年度累計上限: 5,730,000円（標準賞与額の累計上限）
HEALTH_STANDARD_BONUS_LIMIT = Decimal("5730000")
# 厚生年金の月額上限: 1,500,000円（同一月内の標準賞与額合計上限）
PENSION_STANDARD_BONUS_LIMIT = Decimal("1500000")


@dataclass(frozen=True)
class BonusEmployee:
    insured_number: str
    name: str
    payment_date: date
    bonus_amount: Decimal
    fiscal_ytd_standard_bonus: Decimal
    same_month_prior_standard_bonus: Decimal


@dataclass(frozen=True)
class StandardBonusResult:
    bonus_amount: Decimal
    standard_bonus: Decimal
    health_standard_bonus: Decimal
    pension_standard_bonus: Decimal


class StandardBonusService:
    @staticmethod
    def compute_standard_bonus(
        bonus_amount: Decimal,
        fiscal_ytd_standard_bonus: Decimal = Decimal("0"),
        same_month_prior_standard_bonus: Decimal = Decimal("0"),
    ) -> StandardBonusResult:
        if bonus_amount < 0 or fiscal_ytd_standard_bonus < 0 or same_month_prior_standard_bonus < 0:
            raise ValueError("bonus_amount and bonus caps must be non-negative")

        standard_bonus = LaborInsuranceAnnualUpdateService.floor_to_1000(bonus_amount)
        health_remaining = HEALTH_STANDARD_BONUS_LIMIT - fiscal_ytd_standard_bonus
        pension_remaining = PENSION_STANDARD_BONUS_LIMIT - same_month_prior_standard_bonus
        health_standard_bonus = max(Decimal("0"), min(standard_bonus, health_remaining))
        pension_standard_bonus = max(Decimal("0"), min(standard_bonus, pension_remaining))
        return StandardBonusResult(
            bonus_amount=bonus_amount,
            standard_bonus=standard_bonus,
            health_standard_bonus=health_standard_bonus,
            pension_standard_bonus=pension_standard_bonus,
        )

    @classmethod
    def build_csv(cls, employees: list[BonusEmployee]) -> str:
        if not employees:
            raise ValueError("employees must not be empty")

        buffer = StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow([
            "insured_number",
            "name",
            "payment_date",
            "bonus_amount",
            "standard_bonus",
            "health_standard_bonus",
            "pension_standard_bonus",
        ])
        for employee in employees:
            result = cls.compute_standard_bonus(
                bonus_amount=employee.bonus_amount,
                fiscal_ytd_standard_bonus=employee.fiscal_ytd_standard_bonus,
                same_month_prior_standard_bonus=employee.same_month_prior_standard_bonus,
            )
            writer.writerow([
                employee.insured_number,
                employee.name,
                employee.payment_date.isoformat(),
                result.bonus_amount,
                result.standard_bonus,
                result.health_standard_bonus,
                result.pension_standard_bonus,
            ])
        return buffer.getvalue()
