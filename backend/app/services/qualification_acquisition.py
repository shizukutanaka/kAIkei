"""被保険者資格取得届の電子申請連携用データ生成。

This CSV is a structured 連携用データ following 被保険者資格取得届 記載事項.
It is NOT byte-verified against a specific e-Gov CSV仕様書 version and should
be mapped to the exact e-Gov 社会保険手続CSV layout at integration time.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import StringIO

from app.services.standard_remuneration import GradeResult, StandardRemunerationService


@dataclass(frozen=True)
class AcquisitionEmployee:
    insured_number: str
    name: str
    birth_date: date
    qualification_date: date
    estimated_monthly_remuneration: Decimal


@dataclass(frozen=True)
class AcquisitionResult:
    employee: AcquisitionEmployee
    health_grade: GradeResult
    pension_grade: GradeResult


class QualificationAcquisitionService:
    HEADER = [
        "insured_number",
        "name",
        "birth_date",
        "qualification_date",
        "estimated_monthly_remuneration",
        "health_grade",
        "health_standard",
        "pension_grade",
        "pension_standard",
    ]

    @classmethod
    def compute_employee(cls, employee: AcquisitionEmployee) -> AcquisitionResult:
        if employee.estimated_monthly_remuneration < 0:
            raise ValueError("estimated_monthly_remuneration must be non-negative")

        health_grade = StandardRemunerationService.lookup_health_grade(
            employee.estimated_monthly_remuneration,
        )
        pension_grade = StandardRemunerationService.lookup_pension_grade(
            employee.estimated_monthly_remuneration,
        )
        return AcquisitionResult(
            employee=employee,
            health_grade=health_grade,
            pension_grade=pension_grade,
        )

    @classmethod
    def build_csv(cls, employees: list[AcquisitionEmployee]) -> str:
        if not employees:
            raise ValueError("employees must not be empty")

        buffer = StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(cls.HEADER)

        for employee in employees:
            result = cls.compute_employee(employee)
            writer.writerow(
                [
                    employee.insured_number,
                    employee.name,
                    employee.birth_date.isoformat(),
                    employee.qualification_date.isoformat(),
                    employee.estimated_monthly_remuneration,
                    result.health_grade.grade,
                    result.health_grade.standard_monthly_remuneration,
                    result.pension_grade.grade,
                    result.pension_grade.standard_monthly_remuneration,
                ],
            )

        return buffer.getvalue()
