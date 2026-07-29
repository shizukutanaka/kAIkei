"""給与ソフト(給与奉行・弥生給与・freee 等)の賞与データ(CSV)から賞与支払届データを自動生成する。

賞与支払データを取り込み、標準賞与額(千円未満切捨)と上限適用後の健康保険・厚生年金の標準賞与額を
算定して電子申請連携用CSVまで生成する。

    標準賞与額 = floor1000(賞与額)
    健保       = min(標準賞与額, 5,730,000 − 年度累計)   ※年度(4月〜翌3月)の累計上限
    厚年       = min(標準賞与額, 1,500,000 − 同一月内の既支給分)

上限は「年度累計」と「同一月内合計」に対して効くため、同一従業員に複数回の賞与がある場合は
**支給日順に累計を繰り上げながら**判定する必要がある。本サービスは取込ファイル内の複数支給を
支給日昇順に処理して累計を自動計算するので、呼び出し側が累計を用意する必要はない(期首時点で
既に他システムで支給済みの累計があれば `期首累計標準賞与額` 列で持ち込める)。
上限適用と端数処理は既存 `StandardBonusService` に委譲し、CSV列名は `column_map` で上書き可。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import StringIO

from app.services.standard_bonus import BonusEmployee, StandardBonusService

DEFAULT_COLUMN_MAP: dict[str, str] = {
    "insured_number": "被保険者整理番号",
    "name": "氏名",
    "payment_date": "支給年月日",
    "bonus_amount": "賞与額",
    "opening_ytd_standard_bonus": "期首累計標準賞与額",
}


@dataclass(frozen=True)
class BonusRow:
    insured_number: str
    name: str
    payment_date: date
    bonus_amount: Decimal
    opening_ytd_standard_bonus: Decimal


@dataclass(frozen=True)
class BonusPayment:
    insured_number: str
    name: str
    payment_date: date
    bonus_amount: Decimal
    standard_bonus: Decimal
    health_standard_bonus: Decimal
    pension_standard_bonus: Decimal
    fiscal_ytd_standard_bonus: Decimal
    same_month_prior_standard_bonus: Decimal
    health_capped: bool
    pension_capped: bool


@dataclass(frozen=True)
class BonusImportResult:
    payment_count: int
    employee_count: int
    payments: list[BonusPayment]
    total_bonus_amount: Decimal
    total_health_standard_bonus: Decimal
    total_pension_standard_bonus: Decimal
    capped_numbers: list[str]
    csv_text: str


class BonusImportService:
    """賞与データCSVから賞与支払届データを生成する純粋サービス。"""

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
    def _parse_date(value: str | None) -> date:
        if value is None or value.strip() == "":
            raise ValueError("payment_date is required")
        token = value.strip().replace("/", "-")
        try:
            return date.fromisoformat(token)
        except ValueError as exc:
            raise ValueError(f"invalid payment_date value: {value}") from exc

    @staticmethod
    def fiscal_year_range(fiscal_year: int) -> tuple[date, date]:
        """社会保険の年度(4月1日〜翌年3月31日)。"""
        return date(fiscal_year, 4, 1), date(fiscal_year + 1, 3, 31)

    @classmethod
    def parse_csv(
        cls,
        csv_text: str,
        column_map: dict[str, str] | None = None,
    ) -> list[BonusRow]:
        mapping = {**DEFAULT_COLUMN_MAP, **(column_map or {})}
        reader = csv.DictReader(StringIO(csv_text))
        if reader.fieldnames is None:
            raise ValueError("csv has no header row")

        headers = set(reader.fieldnames)
        for key in ("insured_number", "payment_date", "bonus_amount"):
            if mapping[key] not in headers:
                raise ValueError(f"{key} column not found: {mapping[key]}")

        rows: list[BonusRow] = []
        for row in reader:
            insured_number = (row.get(mapping["insured_number"]) or "").strip()
            if insured_number == "":
                raise ValueError("insured_number is required")
            rows.append(
                BonusRow(
                    insured_number=insured_number,
                    name=(row.get(mapping["name"]) or "").strip(),
                    payment_date=cls._parse_date(row.get(mapping["payment_date"])),
                    bonus_amount=cls._parse_decimal(
                        row.get(mapping["bonus_amount"]), field="bonus_amount"
                    ),
                    opening_ytd_standard_bonus=cls._parse_decimal(
                        row.get(mapping["opening_ytd_standard_bonus"]),
                        field="opening_ytd_standard_bonus",
                    ),
                )
            )
        return rows

    @classmethod
    def compute(cls, rows: list[BonusRow], *, fiscal_year: int) -> BonusImportResult:
        if not rows:
            raise ValueError("rows must not be empty")

        start, end = cls.fiscal_year_range(fiscal_year)
        order: list[str] = []
        grouped: dict[str, list[BonusRow]] = {}
        for row in rows:
            if not start <= row.payment_date <= end:
                raise ValueError(
                    f"payment_date {row.payment_date.isoformat()} is outside fiscal year {fiscal_year}"
                )
            if row.insured_number not in grouped:
                order.append(row.insured_number)
                grouped[row.insured_number] = []
            grouped[row.insured_number].append(row)

        payments: list[BonusPayment] = []
        employees: list[BonusEmployee] = []
        capped_numbers: list[str] = []
        total_bonus_amount = Decimal("0")
        total_health = Decimal("0")
        total_pension = Decimal("0")

        for number in order:
            employee_rows = sorted(grouped[number], key=lambda row: row.payment_date)
            ytd = max(row.opening_ytd_standard_bonus for row in employee_rows)
            same_month_totals: dict[tuple[int, int], Decimal] = {}
            capped = False

            for row in employee_rows:
                month_key = (row.payment_date.year, row.payment_date.month)
                same_month_prior = same_month_totals.get(month_key, Decimal("0"))
                result = StandardBonusService.compute_standard_bonus(
                    bonus_amount=row.bonus_amount,
                    fiscal_ytd_standard_bonus=ytd,
                    same_month_prior_standard_bonus=same_month_prior,
                )
                health_capped = result.health_standard_bonus < result.standard_bonus
                pension_capped = result.pension_standard_bonus < result.standard_bonus
                if health_capped or pension_capped:
                    capped = True
                payments.append(
                    BonusPayment(
                        insured_number=number,
                        name=row.name,
                        payment_date=row.payment_date,
                        bonus_amount=result.bonus_amount,
                        standard_bonus=result.standard_bonus,
                        health_standard_bonus=result.health_standard_bonus,
                        pension_standard_bonus=result.pension_standard_bonus,
                        fiscal_ytd_standard_bonus=ytd,
                        same_month_prior_standard_bonus=same_month_prior,
                        health_capped=health_capped,
                        pension_capped=pension_capped,
                    )
                )
                employees.append(
                    BonusEmployee(
                        insured_number=number,
                        name=row.name,
                        payment_date=row.payment_date,
                        bonus_amount=row.bonus_amount,
                        fiscal_ytd_standard_bonus=ytd,
                        same_month_prior_standard_bonus=same_month_prior,
                    )
                )
                ytd += result.health_standard_bonus
                same_month_totals[month_key] = same_month_prior + result.pension_standard_bonus
                total_bonus_amount += result.bonus_amount
                total_health += result.health_standard_bonus
                total_pension += result.pension_standard_bonus

            if capped:
                capped_numbers.append(number)

        return BonusImportResult(
            payment_count=len(payments),
            employee_count=len(order),
            payments=payments,
            total_bonus_amount=total_bonus_amount,
            total_health_standard_bonus=total_health,
            total_pension_standard_bonus=total_pension,
            capped_numbers=capped_numbers,
            csv_text=StandardBonusService.build_csv(employees),
        )
