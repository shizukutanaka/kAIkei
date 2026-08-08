"""給与ソフト(給与奉行・弥生給与・freee 等)の給与データ(CSV)から算定基礎届データを自動生成する。

4〜6月の給与データを従業員別・月別に取り込み、標準報酬月額の定時決定(算定基礎届)に必要な
月別報酬・平均額・等級を算定して電子申請連携用CSVまで生成する。

    月別報酬 = 通貨支給 + 現物支給
    平均額   = 支払基礎日数17日以上の月の報酬合計 ÷ 該当月数 (円未満切捨)
    等級     = 健康保険(50等級)・厚生年金(32等級)の等級表を引く

支払基礎日数17日以上の月が1つも無い従業員は保険者算定等の個別判断が必要なため、平均額を出さず
`requires_manual` を立てて返す(等級を機械的に決めない)。算定・等級表は既存の
`StandardRemunerationService` / `SanteiKisoService` に委譲し、本サービスは取込と整形のみを担う。
CSV列名はソフト毎に異なるため `column_map` で上書き可。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import StringIO

from app.services.santei_export import SanteiEmployee, SanteiKisoService, SanteiMonth

# 定時決定の算定対象月(4・5・6月)
TARGET_MONTHS: tuple[int, ...] = (4, 5, 6)

DEFAULT_COLUMN_MAP: dict[str, str] = {
    "insured_number": "被保険者整理番号",
    "name": "氏名",
    "birth_date": "生年月日",
    "month": "支払月",
    "payment_basis_days": "支払基礎日数",
    "currency_remuneration": "通貨支給",
    "in_kind_remuneration": "現物支給",
    "previous_health_standard": "従前健保標準報酬",
    "previous_pension_standard": "従前厚年標準報酬",
}


@dataclass(frozen=True)
class SanteiWageRow:
    insured_number: str
    name: str
    birth_date: date
    month: int
    payment_basis_days: int
    currency_remuneration: Decimal
    in_kind_remuneration: Decimal
    previous_health_standard: Decimal
    previous_pension_standard: Decimal


@dataclass(frozen=True)
class SanteiImportEmployee:
    insured_number: str
    name: str
    month_totals: list[Decimal]
    total: Decimal
    average: Decimal | None
    health_grade: int | None
    health_standard: Decimal | None
    pension_grade: int | None
    pension_standard: Decimal | None
    requires_manual: bool


@dataclass(frozen=True)
class SanteiImportResult:
    row_count: int
    employee_count: int
    employees: list[SanteiImportEmployee]
    manual_review_numbers: list[str]
    csv_text: str


class SanteiImportService:
    """給与データCSVから算定基礎届データを生成する純粋サービス。"""

    @staticmethod
    def _parse_decimal(value: str | None, *, field: str) -> Decimal:
        if value is None:
            return Decimal("0")
        token = value.strip().replace(",", "").replace("¥", "").replace("￥", "")
        if token == "":
            return Decimal("0")
        try:
            parsed = Decimal(token)
        except ArithmeticError as exc:
            raise ValueError(f"invalid {field} value: {value}") from exc
        if parsed < 0:
            raise ValueError(f"{field} must not be negative")
        return parsed

    @staticmethod
    def _parse_int(value: str | None, *, field: str) -> int:
        if value is None or value.strip() == "":
            raise ValueError(f"{field} is required")
        token = "".join(ch for ch in value.strip() if ch.isdigit())
        if token == "":
            raise ValueError(f"invalid {field} value: {value}")
        return int(token)

    @staticmethod
    def _parse_date(value: str | None) -> date:
        if value is None or value.strip() == "":
            raise ValueError("birth_date is required")
        token = value.strip().replace("/", "-")
        try:
            return date.fromisoformat(token)
        except ValueError as exc:
            raise ValueError(f"invalid birth_date value: {value}") from exc

    @classmethod
    def parse_csv(
        cls,
        csv_text: str,
        column_map: dict[str, str] | None = None,
    ) -> list[SanteiWageRow]:
        mapping = {**DEFAULT_COLUMN_MAP, **(column_map or {})}
        reader = csv.DictReader(StringIO(csv_text))
        if reader.fieldnames is None:
            raise ValueError("csv has no header row")

        headers = set(reader.fieldnames)
        for key in ("insured_number", "birth_date", "month", "payment_basis_days", "currency_remuneration"):
            if mapping[key] not in headers:
                raise ValueError(f"{key} column not found: {mapping[key]}")

        rows: list[SanteiWageRow] = []
        for row in reader:
            insured_number = (row.get(mapping["insured_number"]) or "").strip()
            if insured_number == "":
                raise ValueError("insured_number is required")
            month = cls._parse_int(row.get(mapping["month"]), field="month")
            if month not in TARGET_MONTHS:
                raise ValueError(f"month must be one of {list(TARGET_MONTHS)}: {month}")
            rows.append(
                SanteiWageRow(
                    insured_number=insured_number,
                    name=(row.get(mapping["name"]) or "").strip(),
                    birth_date=cls._parse_date(row.get(mapping["birth_date"])),
                    month=month,
                    payment_basis_days=cls._parse_int(
                        row.get(mapping["payment_basis_days"]), field="payment_basis_days"
                    ),
                    currency_remuneration=cls._parse_decimal(
                        row.get(mapping["currency_remuneration"]), field="currency_remuneration"
                    ),
                    in_kind_remuneration=cls._parse_decimal(
                        row.get(mapping["in_kind_remuneration"]), field="in_kind_remuneration"
                    ),
                    previous_health_standard=cls._parse_decimal(
                        row.get(mapping["previous_health_standard"]), field="previous_health_standard"
                    ),
                    previous_pension_standard=cls._parse_decimal(
                        row.get(mapping["previous_pension_standard"]), field="previous_pension_standard"
                    ),
                )
            )
        return rows

    @classmethod
    def build_employees(
        cls,
        rows: list[SanteiWageRow],
        *,
        applicable_year: int,
        applicable_month: int,
    ) -> list[SanteiEmployee]:
        if not rows:
            raise ValueError("rows must not be empty")

        order: list[str] = []
        heads: dict[str, SanteiWageRow] = {}
        months: dict[str, dict[int, SanteiWageRow]] = {}

        for row in rows:
            number = row.insured_number
            if number not in heads:
                order.append(number)
                heads[number] = row
                months[number] = {}
            elif heads[number].birth_date != row.birth_date:
                raise ValueError(f"inconsistent birth_date for insured_number: {number}")
            if row.month in months[number]:
                raise ValueError(f"duplicate month {row.month} for insured_number: {number}")
            months[number][row.month] = row

        employees: list[SanteiEmployee] = []
        for number in order:
            head = heads[number]
            employees.append(
                SanteiEmployee(
                    insured_number=number,
                    name=head.name,
                    birth_date=head.birth_date,
                    previous_health_standard=head.previous_health_standard,
                    previous_pension_standard=head.previous_pension_standard,
                    applicable_year=applicable_year,
                    applicable_month=applicable_month,
                    months=[
                        SanteiMonth(
                            payment_basis_days=months[number][month].payment_basis_days,
                            currency_remuneration=months[number][month].currency_remuneration,
                            in_kind_remuneration=months[number][month].in_kind_remuneration,
                        )
                        for month in TARGET_MONTHS
                        if month in months[number]
                    ],
                )
            )
        return employees

    @classmethod
    def compute(
        cls,
        rows: list[SanteiWageRow],
        *,
        applicable_year: int,
        applicable_month: int = 9,
    ) -> SanteiImportResult:
        employees = cls.build_employees(
            rows,
            applicable_year=applicable_year,
            applicable_month=applicable_month,
        )

        summaries: list[SanteiImportEmployee] = []
        manual_review_numbers: list[str] = []
        for employee in employees:
            result = SanteiKisoService.compute_employee(employee)
            if result.requires_manual:
                manual_review_numbers.append(employee.insured_number)
            summaries.append(
                SanteiImportEmployee(
                    insured_number=employee.insured_number,
                    name=employee.name,
                    month_totals=result.month_totals,
                    total=result.total,
                    average=result.average,
                    health_grade=result.health_grade.grade if result.health_grade else None,
                    health_standard=(
                        result.health_grade.standard_monthly_remuneration if result.health_grade else None
                    ),
                    pension_grade=result.pension_grade.grade if result.pension_grade else None,
                    pension_standard=(
                        result.pension_grade.standard_monthly_remuneration if result.pension_grade else None
                    ),
                    requires_manual=result.requires_manual,
                )
            )

        return SanteiImportResult(
            row_count=len(rows),
            employee_count=len(employees),
            employees=summaries,
            manual_review_numbers=manual_review_numbers,
            csv_text=SanteiKisoService.build_csv(employees),
        )
