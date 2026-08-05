"""給与ソフト(給与奉行・弥生給与・freee 等)の給与データ(CSV)から労働保険料を自動計算する。

給与データを取り込み、従業員別に賃金を合算して労働保険の賃金総額を集計し、確定保険料
(労災・雇用)と一般拠出金を算定する。年度更新申告書では賃金総額を労災保険分と雇用保険分に
分ける必要がある(雇用保険は被保険者のみが対象で、役員・昼間学生・週20時間未満の短時間労働者
等は除かれる)。本サービスは各行に付与された対象区分に従い、次の2つの賃金総額を別々に集計する。

    労災保険分の賃金総額 = 労災対象の全労働者の賃金合計
    雇用保険分の賃金総額 = 雇用保険被保険者の賃金合計

確定保険料の算定(年度更新):
    労災保険料 = floor_1000(労災賃金総額) × 労災保険率
    雇用保険料 = floor_1000(雇用賃金総額) × (被保険者負担率 + 事業主負担率)
    一般拠出金 = floor_1000(労災賃金総額) × 0.00002 (石綿健康被害救済法)

CSV の列名はソフトごとに異なるため、列マッピングを引数で上書きできる(既定は汎用的な日本語
見出し)。対象区分の列が CSV に存在しない場合は全員を対象(労災・雇用とも)として扱う。
料率は年度により改定されるため既定値は参考値とし、LaborInsuranceService のカタログに委譲する。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from io import StringIO

from app.services.labor_insurance import (
    DEFAULT_WORKERS_COMPENSATION_RATE,
    LaborInsuranceService,
)
from app.services.labor_insurance_annual import GENERAL_CONTRIBUTION_RATE

_TRUE_TOKENS = frozenset({"1", "true", "yes", "対象", "有", "あり", "はい", "○", "◯"})
_FALSE_TOKENS = frozenset({"0", "false", "no", "対象外", "無", "なし", "いいえ", "×", "-"})

DEFAULT_COLUMN_MAP: dict[str, str] = {
    "employee_id": "社員番号",
    "wage": "賃金",
    "employment_insured": "雇用保険対象",
    "workers_comp_insured": "労災対象",
}


@dataclass(frozen=True)
class WageRecord:
    employee_id: str
    wage: Decimal
    employment_insured: bool
    workers_comp_insured: bool


@dataclass(frozen=True)
class ImportedLaborInsuranceResult:
    row_count: int
    employee_count: int
    employment_insured_count: int
    workers_comp_wage_total: Decimal
    employment_wage_total: Decimal
    workers_comp_base: Decimal
    employment_base: Decimal
    workers_comp_premium: Decimal
    employment_premium: Decimal
    employment_employee_premium: Decimal
    employment_employer_premium: Decimal
    general_contribution: Decimal
    determined_premium: Decimal


class PayrollWageImportService:
    """給与ソフトの給与データから労働保険料を集計・算定する純粋サービス。"""

    @staticmethod
    def _floor_1000(amount: Decimal) -> Decimal:
        return (amount // Decimal("1000")) * Decimal("1000")

    @staticmethod
    def _floor_yen(amount: Decimal) -> Decimal:
        return amount.quantize(Decimal("1"), rounding=ROUND_DOWN)

    @staticmethod
    def _parse_flag(value: str | None, *, default: bool) -> bool:
        if value is None:
            return default
        token = value.strip()
        if token == "":
            return default
        lowered = token.lower()
        if lowered in _TRUE_TOKENS or token in _TRUE_TOKENS:
            return True
        if lowered in _FALSE_TOKENS or token in _FALSE_TOKENS:
            return False
        raise ValueError(f"unrecognized insured flag: {value}")

    @staticmethod
    def _parse_wage(value: str | None) -> Decimal:
        if value is None:
            raise ValueError("wage column is missing")
        token = value.strip().replace(",", "").replace("¥", "").replace("￥", "")
        if token == "":
            return Decimal("0")
        try:
            wage = Decimal(token)
        except (ArithmeticError, ValueError) as exc:
            raise ValueError(f"invalid wage value: {value}") from exc
        if wage < 0:
            raise ValueError("wage must not be negative")
        return wage

    @classmethod
    def parse_csv(
        cls,
        csv_text: str,
        column_map: dict[str, str] | None = None,
    ) -> list[WageRecord]:
        mapping = {**DEFAULT_COLUMN_MAP, **(column_map or {})}
        reader = csv.DictReader(StringIO(csv_text))
        if reader.fieldnames is None:
            raise ValueError("csv has no header row")

        headers = set(reader.fieldnames)
        wage_col = mapping["wage"]
        if wage_col not in headers:
            raise ValueError(f"wage column not found: {wage_col}")
        id_col = mapping["employee_id"]
        emp_col = mapping["employment_insured"]
        wc_col = mapping["workers_comp_insured"]
        has_emp_col = emp_col in headers
        has_wc_col = wc_col in headers

        records: list[WageRecord] = []
        for idx, row in enumerate(reader):
            employee_id = (row.get(id_col) or "").strip() or f"row-{idx}"
            wage = cls._parse_wage(row.get(wage_col))
            employment_insured = cls._parse_flag(
                row.get(emp_col) if has_emp_col else None, default=True
            )
            workers_comp_insured = cls._parse_flag(
                row.get(wc_col) if has_wc_col else None, default=True
            )
            records.append(
                WageRecord(
                    employee_id=employee_id,
                    wage=wage,
                    employment_insured=employment_insured,
                    workers_comp_insured=workers_comp_insured,
                )
            )
        return records

    @classmethod
    def compute(
        cls,
        records: list[WageRecord],
        *,
        business_type: str,
        workers_comp_rate: Decimal = DEFAULT_WORKERS_COMPENSATION_RATE,
    ) -> ImportedLaborInsuranceResult:
        if not records:
            raise ValueError("records must not be empty")
        if workers_comp_rate < 0:
            raise ValueError("workers_comp_rate must not be negative")

        employee_rate, employer_rate = LaborInsuranceService._employment_rates(business_type)

        employee_ids: set[str] = set()
        employment_ids: set[str] = set()
        workers_comp_wage_total = Decimal("0")
        employment_wage_total = Decimal("0")

        for record in records:
            employee_ids.add(record.employee_id)
            if record.workers_comp_insured:
                workers_comp_wage_total += record.wage
            if record.employment_insured:
                employment_wage_total += record.wage
                employment_ids.add(record.employee_id)

        workers_comp_base = cls._floor_1000(workers_comp_wage_total)
        employment_base = cls._floor_1000(employment_wage_total)

        workers_comp_premium = cls._floor_yen(workers_comp_base * workers_comp_rate)
        employment_employee_premium = cls._floor_yen(employment_base * employee_rate)
        employment_employer_premium = cls._floor_yen(employment_base * employer_rate)
        employment_premium = employment_employee_premium + employment_employer_premium
        general_contribution = cls._floor_yen(workers_comp_base * GENERAL_CONTRIBUTION_RATE)
        determined_premium = workers_comp_premium + employment_premium

        return ImportedLaborInsuranceResult(
            row_count=len(records),
            employee_count=len(employee_ids),
            employment_insured_count=len(employment_ids),
            workers_comp_wage_total=workers_comp_wage_total,
            employment_wage_total=employment_wage_total,
            workers_comp_base=workers_comp_base,
            employment_base=employment_base,
            workers_comp_premium=workers_comp_premium,
            employment_premium=employment_premium,
            employment_employee_premium=employment_employee_premium,
            employment_employer_premium=employment_employer_premium,
            general_contribution=general_contribution,
            determined_premium=determined_premium,
        )
