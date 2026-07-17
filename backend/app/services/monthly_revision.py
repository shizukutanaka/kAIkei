"""月額変更届の電子申請連携用データ生成。

This CSV is a structured 連携用データ following 月額変更届 記載事項.
It is NOT byte-verified against a specific e-Gov CSV仕様書 version and should
be mapped to the exact e-Gov 社会保険手続CSV layout at integration time.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from io import StringIO

from app.services.standard_remuneration import GradeResult, RemunerationMonth, StandardRemunerationService


@dataclass(frozen=True)
class RevisionEmployee:
    insured_number: str
    name: str
    previous_health_standard: Decimal
    previous_pension_standard: Decimal
    fixed_wage_changed: bool
    months: list[RemunerationMonth]


@dataclass(frozen=True)
class MonthlyRevisionResult:
    insured_number: str
    name: str
    previous_health_standard: Decimal
    previous_pension_standard: Decimal
    prev_health: GradeResult
    prev_pension: GradeResult
    average: Decimal | None
    new_health: GradeResult | None
    new_pension: GradeResult | None
    health_grade_diff: int
    fixed_wage_changed: bool
    days_ok: bool
    revision_required: bool
    reason: str


class MonthlyRevisionService:
    @classmethod
    def judge(
        cls,
        previous_health_standard: Decimal,
        previous_pension_standard: Decimal,
        months: list[RemunerationMonth],
        fixed_wage_changed: bool,
        min_payment_basis_days: int = 17,
    ) -> MonthlyRevisionResult:
        if len(months) != 3:
            raise ValueError("months must contain exactly 3 items")
        if previous_health_standard < 0 or previous_pension_standard < 0:
            raise ValueError("previous standards must be non-negative")

        for month in months:
            if month.payment_basis_days < 0 or month.remuneration < 0:
                raise ValueError("months must be non-negative")

        days_ok = all(month.payment_basis_days >= min_payment_basis_days for month in months)
        average = (
            StandardRemunerationService.determine_remuneration_monthly(months, min_payment_basis_days)
            if days_ok
            else None
        )

        prev_health = StandardRemunerationService.lookup_health_grade(previous_health_standard)
        prev_pension = StandardRemunerationService.lookup_pension_grade(previous_pension_standard)

        new_health = None
        new_pension = None
        health_grade_diff = 0
        if average is not None:
            new_health = StandardRemunerationService.lookup_health_grade(average)
            new_pension = StandardRemunerationService.lookup_pension_grade(average)
            health_grade_diff = abs(new_health.grade - prev_health.grade)

        revision_required = fixed_wage_changed and days_ok and health_grade_diff >= 2
        if revision_required:
            reason = "eligible"
        elif not fixed_wage_changed:
            reason = "fixed_wage_not_changed"
        elif not days_ok:
            reason = "insufficient_days"
        else:
            reason = "grade_diff_below_2"

        return MonthlyRevisionResult(
            insured_number="",
            name="",
            previous_health_standard=previous_health_standard,
            previous_pension_standard=previous_pension_standard,
            prev_health=prev_health,
            prev_pension=prev_pension,
            average=average,
            new_health=new_health,
            new_pension=new_pension,
            health_grade_diff=health_grade_diff,
            fixed_wage_changed=fixed_wage_changed,
            days_ok=days_ok,
            revision_required=revision_required,
            reason=reason,
        )

    @classmethod
    def compute_employee(cls, employee: RevisionEmployee, min_payment_basis_days: int = 17) -> MonthlyRevisionResult:
        result = cls.judge(
            previous_health_standard=employee.previous_health_standard,
            previous_pension_standard=employee.previous_pension_standard,
            months=employee.months,
            fixed_wage_changed=employee.fixed_wage_changed,
            min_payment_basis_days=min_payment_basis_days,
        )
        return MonthlyRevisionResult(
            insured_number=employee.insured_number,
            name=employee.name,
            previous_health_standard=result.previous_health_standard,
            previous_pension_standard=result.previous_pension_standard,
            prev_health=result.prev_health,
            prev_pension=result.prev_pension,
            average=result.average,
            new_health=result.new_health,
            new_pension=result.new_pension,
            health_grade_diff=result.health_grade_diff,
            fixed_wage_changed=result.fixed_wage_changed,
            days_ok=result.days_ok,
            revision_required=result.revision_required,
            reason=result.reason,
        )

    @classmethod
    def build_csv(cls, employees: list[RevisionEmployee]) -> str:
        if not employees:
            raise ValueError("employees must not be empty")

        buffer = StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow([
            "insured_number",
            "name",
            "fixed_wage_changed",
            "days_ok",
            "average",
            "prev_health_grade",
            "new_health_grade",
            "health_grade_diff",
            "prev_pension_grade",
            "new_pension_grade",
            "revision_required",
            "reason",
        ])
        for employee in employees:
            result = cls.compute_employee(employee)
            writer.writerow([
                result.insured_number,
                result.name,
                result.fixed_wage_changed,
                result.days_ok,
                result.average if result.average is not None else "",
                result.prev_health.grade,
                result.new_health.grade if result.new_health is not None else "",
                result.health_grade_diff,
                result.prev_pension.grade,
                result.new_pension.grade if result.new_pension is not None else "",
                result.revision_required,
                result.reason,
            ])
        return buffer.getvalue()
