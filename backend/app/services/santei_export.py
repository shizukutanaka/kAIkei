"""算定基礎届の電子申請連携用データ生成。

This CSV is a structured 連携用データ following the 算定基礎届 記載事項.
It is NOT byte-verified against a specific e-Gov CSV仕様書 version and should
be mapped to the exact e-Gov 社会保険手続CSV layout at integration time.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import StringIO

from app.services.standard_remuneration import GradeResult, RemunerationMonth, StandardRemunerationService


@dataclass(frozen=True)
class SanteiMonth:
    payment_basis_days: int
    currency_remuneration: Decimal
    in_kind_remuneration: Decimal


@dataclass(frozen=True)
class SanteiEmployee:
    insured_number: str
    name: str
    birth_date: date
    previous_health_standard: Decimal
    previous_pension_standard: Decimal
    applicable_year: int
    applicable_month: int
    months: list[SanteiMonth]


@dataclass(frozen=True)
class SanteiEmployeeResult:
    employee: SanteiEmployee
    month_totals: list[Decimal]
    total: Decimal
    average: Decimal | None
    health_grade: GradeResult | None
    pension_grade: GradeResult | None
    requires_manual: bool


class SanteiKisoService:
    HEADER = [
        "insured_number",
        "name",
        "birth_date",
        "applicable_ym",
        "previous_health_standard",
        "previous_pension_standard",
        "apr_payment_basis_days",
        "apr_currency_remuneration",
        "apr_in_kind_remuneration",
        "apr_total",
        "may_payment_basis_days",
        "may_currency_remuneration",
        "may_in_kind_remuneration",
        "may_total",
        "jun_payment_basis_days",
        "jun_currency_remuneration",
        "jun_in_kind_remuneration",
        "jun_total",
        "total",
        "average",
        "health_grade",
        "health_standard",
        "pension_grade",
        "pension_standard",
        "requires_manual",
    ]

    @staticmethod
    def _month_total(month: SanteiMonth) -> Decimal:
        return month.currency_remuneration + month.in_kind_remuneration

    @classmethod
    def compute_employee(cls, emp: SanteiEmployee) -> SanteiEmployeeResult:
        if not emp.months:
            raise ValueError("months must not be empty")

        month_totals = [cls._month_total(month) for month in emp.months]
        remuneration_months = [
            RemunerationMonth(payment_basis_days=month.payment_basis_days, remuneration=total)
            for month, total in zip(emp.months, month_totals, strict=False)
        ]
        average = StandardRemunerationService.determine_remuneration_monthly(remuneration_months)
        total = sum(
            (
                total
                for month, total in zip(emp.months, month_totals, strict=False)
                if month.payment_basis_days >= 17
            ),
            Decimal("0"),
        )

        if average is None:
            return SanteiEmployeeResult(
                employee=emp,
                month_totals=month_totals,
                total=total,
                average=None,
                health_grade=None,
                pension_grade=None,
                requires_manual=True,
            )

        health_grade = StandardRemunerationService.lookup_health_grade(average)
        pension_grade = StandardRemunerationService.lookup_pension_grade(average)
        return SanteiEmployeeResult(
            employee=emp,
            month_totals=month_totals,
            total=total,
            average=average,
            health_grade=health_grade,
            pension_grade=pension_grade,
            requires_manual=False,
        )

    @classmethod
    def build_csv(cls, employees: list[SanteiEmployee]) -> str:
        if not employees:
            raise ValueError("employees must not be empty")

        buffer = StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(cls.HEADER)

        for emp in employees:
            result = cls.compute_employee(emp)
            months = list(emp.months[:3])
            month_totals = list(result.month_totals[:3])
            while len(months) < 3:
                months.append(SanteiMonth(payment_basis_days=0, currency_remuneration=Decimal("0"), in_kind_remuneration=Decimal("0")))
            while len(month_totals) < 3:
                month_totals.append(Decimal("0"))
            month_rows = []
            for month, total in zip(months, month_totals, strict=False):
                month_rows.extend(
                    [
                        month.payment_basis_days,
                        month.currency_remuneration,
                        month.in_kind_remuneration,
                        total,
                    ]
                )
            writer.writerow(
                [
                    emp.insured_number,
                    emp.name,
                    emp.birth_date.isoformat(),
                    f"{emp.applicable_year:04d}-{emp.applicable_month:02d}",
                    emp.previous_health_standard,
                    emp.previous_pension_standard,
                    *month_rows,
                    result.total,
                    result.average if result.average is not None else "",
                    result.health_grade.grade if result.health_grade is not None else "",
                    result.health_grade.standard_monthly_remuneration if result.health_grade is not None else "",
                    result.pension_grade.grade if result.pension_grade is not None else "",
                    result.pension_grade.standard_monthly_remuneration if result.pension_grade is not None else "",
                    result.requires_manual,
                ]
            )

        return buffer.getvalue()
