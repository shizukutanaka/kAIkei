"""給与ソフト(給与奉行・弥生給与・freee 等)の給与データ(CSV)から月額変更届(随時改定)の対象者を自動抽出する。

昇給・降給等で固定的賃金が変動した月以降の3か月分の給与データを従業員別に取り込み、随時改定
(健康保険法43条・厚生年金保険法23条)の3要件を判定する。

    1. 固定的賃金の変動があった
    2. 3か月すべて支払基礎日数17日以上
    3. 変動後3か月の平均報酬から求めた標準報酬月額が従前と2等級以上差がある

改定月は変動月から4か月目(3か月の起算月 + 3)で、年跨ぎ(12・1・2月 → 翌年3月改定)も扱う。
3か月は連続していなければならないため、欠落・重複・不連続は取込エラーとする。判定と等級表は既存の
`MonthlyRevisionService` / `StandardRemunerationService` に委譲し、本サービスは取込と整形のみを担う。
CSV列名はソフト毎に異なるため `column_map` で上書き可。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from io import StringIO

from app.services.monthly_revision import MonthlyRevisionService, RevisionEmployee
from app.services.standard_remuneration import RemunerationMonth

# 随時改定の算定対象は変動月以降の3か月
REVISION_MONTH_COUNT = 3

_TRUE_TOKENS = frozenset({"1", "true", "yes", "有", "あり", "変動", "はい", "○", "◯"})
_FALSE_TOKENS = frozenset({"0", "false", "no", "無", "なし", "変動なし", "いいえ", "×", "-", ""})

DEFAULT_COLUMN_MAP: dict[str, str] = {
    "insured_number": "被保険者整理番号",
    "name": "氏名",
    "month": "支払月",
    "payment_basis_days": "支払基礎日数",
    "currency_remuneration": "通貨支給",
    "in_kind_remuneration": "現物支給",
    "previous_health_standard": "従前健保標準報酬",
    "previous_pension_standard": "従前厚年標準報酬",
    "fixed_wage_changed": "固定的賃金変動",
}


@dataclass(frozen=True)
class RevisionWageRow:
    insured_number: str
    name: str
    month: int
    payment_basis_days: int
    currency_remuneration: Decimal
    in_kind_remuneration: Decimal
    previous_health_standard: Decimal
    previous_pension_standard: Decimal
    fixed_wage_changed: bool


@dataclass(frozen=True)
class RevisionImportEmployee:
    insured_number: str
    name: str
    start_month: int
    revision_year_month: str
    month_totals: list[Decimal]
    average: Decimal | None
    prev_health_grade: int
    new_health_grade: int | None
    health_grade_diff: int
    prev_pension_grade: int
    new_pension_grade: int | None
    new_health_standard: Decimal | None
    new_pension_standard: Decimal | None
    fixed_wage_changed: bool
    days_ok: bool
    revision_required: bool
    reason: str


@dataclass(frozen=True)
class RevisionImportResult:
    row_count: int
    employee_count: int
    employees: list[RevisionImportEmployee]
    revision_required_numbers: list[str]
    csv_text: str


class RevisionImportService:
    """給与データCSVから随時改定(月額変更届)の対象者を判定する純粋サービス。"""

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
    def _parse_bool(value: str | None) -> bool:
        token = (value or "").strip().lower()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
        raise ValueError(f"invalid fixed_wage_changed value: {value}")

    @classmethod
    def parse_csv(
        cls,
        csv_text: str,
        column_map: dict[str, str] | None = None,
    ) -> list[RevisionWageRow]:
        mapping = {**DEFAULT_COLUMN_MAP, **(column_map or {})}
        reader = csv.DictReader(StringIO(csv_text))
        if reader.fieldnames is None:
            raise ValueError("csv has no header row")

        headers = set(reader.fieldnames)
        for key in ("insured_number", "month", "payment_basis_days", "currency_remuneration"):
            if mapping[key] not in headers:
                raise ValueError(f"{key} column not found: {mapping[key]}")

        rows: list[RevisionWageRow] = []
        for row in reader:
            insured_number = (row.get(mapping["insured_number"]) or "").strip()
            if insured_number == "":
                raise ValueError("insured_number is required")
            month = cls._parse_int(row.get(mapping["month"]), field="month")
            if not 1 <= month <= 12:
                raise ValueError(f"month must be between 1 and 12: {month}")
            rows.append(
                RevisionWageRow(
                    insured_number=insured_number,
                    name=(row.get(mapping["name"]) or "").strip(),
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
                    fixed_wage_changed=cls._parse_bool(row.get(mapping["fixed_wage_changed"])),
                )
            )
        return rows

    @staticmethod
    def _ordered_months(months: set[int], insured_number: str) -> list[int]:
        """3か月が連続する並び(年跨ぎを含む)を返す。連続していなければエラー。"""
        for start in sorted(months):
            sequence = [(start - 1 + offset) % 12 + 1 for offset in range(REVISION_MONTH_COUNT)]
            if set(sequence) == months:
                return sequence
        raise ValueError(f"months must be 3 consecutive months for insured_number: {insured_number}")

    @classmethod
    def compute(cls, rows: list[RevisionWageRow], *, start_year: int) -> RevisionImportResult:
        if not rows:
            raise ValueError("rows must not be empty")

        order: list[str] = []
        heads: dict[str, RevisionWageRow] = {}
        by_month: dict[str, dict[int, RevisionWageRow]] = {}

        for row in rows:
            number = row.insured_number
            if number not in heads:
                order.append(number)
                heads[number] = row
                by_month[number] = {}
            if row.month in by_month[number]:
                raise ValueError(f"duplicate month {row.month} for insured_number: {number}")
            by_month[number][row.month] = row

        employees: list[RevisionEmployee] = []
        month_sequences: dict[str, list[int]] = {}
        for number in order:
            months = by_month[number]
            if len(months) != REVISION_MONTH_COUNT:
                raise ValueError(
                    f"insured_number {number} must have exactly {REVISION_MONTH_COUNT} months, got {len(months)}"
                )
            sequence = cls._ordered_months(set(months), number)
            month_sequences[number] = sequence
            head = heads[number]
            employees.append(
                RevisionEmployee(
                    insured_number=number,
                    name=head.name,
                    previous_health_standard=head.previous_health_standard,
                    previous_pension_standard=head.previous_pension_standard,
                    fixed_wage_changed=head.fixed_wage_changed,
                    months=[
                        RemunerationMonth(
                            payment_basis_days=months[month].payment_basis_days,
                            remuneration=months[month].currency_remuneration
                            + months[month].in_kind_remuneration,
                        )
                        for month in sequence
                    ],
                )
            )

        summaries: list[RevisionImportEmployee] = []
        revision_required_numbers: list[str] = []
        for employee in employees:
            result = MonthlyRevisionService.compute_employee(employee)
            start_month = month_sequences[employee.insured_number][0]
            revision_month_index = start_month - 1 + REVISION_MONTH_COUNT
            revision_year = start_year + revision_month_index // 12
            revision_month = revision_month_index % 12 + 1
            if result.revision_required:
                revision_required_numbers.append(employee.insured_number)
            summaries.append(
                RevisionImportEmployee(
                    insured_number=employee.insured_number,
                    name=employee.name,
                    start_month=start_month,
                    revision_year_month=f"{revision_year:04d}-{revision_month:02d}",
                    month_totals=[month.remuneration for month in employee.months],
                    average=result.average,
                    prev_health_grade=result.prev_health.grade,
                    new_health_grade=result.new_health.grade if result.new_health else None,
                    health_grade_diff=result.health_grade_diff,
                    prev_pension_grade=result.prev_pension.grade,
                    new_pension_grade=result.new_pension.grade if result.new_pension else None,
                    new_health_standard=(
                        result.new_health.standard_monthly_remuneration if result.new_health else None
                    ),
                    new_pension_standard=(
                        result.new_pension.standard_monthly_remuneration if result.new_pension else None
                    ),
                    fixed_wage_changed=result.fixed_wage_changed,
                    days_ok=result.days_ok,
                    revision_required=result.revision_required,
                    reason=result.reason,
                )
            )

        return RevisionImportResult(
            row_count=len(rows),
            employee_count=len(employees),
            employees=summaries,
            revision_required_numbers=revision_required_numbers,
            csv_text=MonthlyRevisionService.build_csv(employees),
        )
