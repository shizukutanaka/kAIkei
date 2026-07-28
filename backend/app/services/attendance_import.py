"""勤怠ソフト(KING OF TIME・ジョブカン・タッチオンタイム 等)の勤怠データ(CSV)から割増賃金を自動計算する。

勤怠データを取り込み、従業員別に時間外・深夜・休日労働時間を合算して労働基準法37条の割増賃金を
算定する。月60時間超の時間外労働は割増率が1.25→1.50に上がるため、合算後の月間時間外を60時間で
分割してから `OvertimePayService` に委譲する(分割前に行ごとに計算すると、月次合計が60時間を超えて
いても各行が60時間以下のため割増率が上がらず過少計算になる)。

    60時間以内の時間外 = min(月間時間外, 60)
    60時間超の時間外   = max(月間時間外 − 60, 0)

CSV の列名はソフトごとに異なるため列マッピングを引数で上書きできる(既定は汎用的な日本語見出し)。
時間の列が存在しない場合は0時間として扱う。時給は従業員ごとに一定である必要があり、同一従業員に
異なる時給が現れた場合は取込エラーとする(月中の賃金改定は別の月として取り込む想定)。
36協定の管理に使えるよう、月間時間外が45時間を超えた従業員にはフラグを立てる。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from io import StringIO

from app.services.overtime_pay import OvertimePayService

# 労働基準法37条: 月60時間を超える時間外労働は割増率が上がる
OVERTIME_MONTHLY_THRESHOLD = Decimal("60")
# 労働基準法36条: 36協定の原則的な上限(月45時間)
OVERTIME_MONTHLY_WARNING = Decimal("45")

DEFAULT_COLUMN_MAP: dict[str, str] = {
    "employee_id": "社員番号",
    "hourly_wage": "時給",
    "overtime_hours": "時間外",
    "late_night_hours": "深夜",
    "holiday_hours": "休日",
}


@dataclass(frozen=True)
class AttendanceRecord:
    employee_id: str
    hourly_wage: Decimal
    overtime_hours: Decimal
    late_night_hours: Decimal
    holiday_hours: Decimal


@dataclass(frozen=True)
class EmployeeOvertimePay:
    employee_id: str
    hourly_wage: Decimal
    overtime_hours: Decimal
    overtime_within_60_hours: Decimal
    overtime_over_60_hours: Decimal
    late_night_hours: Decimal
    holiday_hours: Decimal
    overtime_pay: Decimal
    overtime_over_60_pay: Decimal
    late_night_pay: Decimal
    holiday_pay: Decimal
    total_premium: Decimal
    exceeds_45_hours: bool


@dataclass(frozen=True)
class AttendanceImportResult:
    row_count: int
    employee_count: int
    employees: list[EmployeeOvertimePay]
    total_premium: Decimal
    exceeding_employee_ids: list[str]


class AttendanceImportService:
    """勤怠ソフトの勤怠データから割増賃金を集計・算定する純粋サービス。"""

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

    @classmethod
    def parse_csv(
        cls,
        csv_text: str,
        column_map: dict[str, str] | None = None,
    ) -> list[AttendanceRecord]:
        mapping = {**DEFAULT_COLUMN_MAP, **(column_map or {})}
        reader = csv.DictReader(StringIO(csv_text))
        if reader.fieldnames is None:
            raise ValueError("csv has no header row")

        headers = set(reader.fieldnames)
        wage_col = mapping["hourly_wage"]
        if wage_col not in headers:
            raise ValueError(f"hourly_wage column not found: {wage_col}")
        id_col = mapping["employee_id"]

        records: list[AttendanceRecord] = []
        for idx, row in enumerate(reader):
            employee_id = (row.get(id_col) or "").strip() or f"row-{idx}"
            records.append(
                AttendanceRecord(
                    employee_id=employee_id,
                    hourly_wage=cls._parse_decimal(row.get(wage_col), field="hourly_wage"),
                    overtime_hours=cls._parse_decimal(
                        row.get(mapping["overtime_hours"]), field="overtime_hours"
                    ),
                    late_night_hours=cls._parse_decimal(
                        row.get(mapping["late_night_hours"]), field="late_night_hours"
                    ),
                    holiday_hours=cls._parse_decimal(
                        row.get(mapping["holiday_hours"]), field="holiday_hours"
                    ),
                )
            )
        return records

    @classmethod
    def compute(cls, records: list[AttendanceRecord]) -> AttendanceImportResult:
        if not records:
            raise ValueError("records must not be empty")

        wages: dict[str, Decimal] = {}
        overtime: dict[str, Decimal] = {}
        late_night: dict[str, Decimal] = {}
        holiday: dict[str, Decimal] = {}
        order: list[str] = []

        for record in records:
            employee_id = record.employee_id
            if employee_id not in wages:
                order.append(employee_id)
                wages[employee_id] = record.hourly_wage
                overtime[employee_id] = Decimal("0")
                late_night[employee_id] = Decimal("0")
                holiday[employee_id] = Decimal("0")
            elif wages[employee_id] != record.hourly_wage:
                raise ValueError(f"inconsistent hourly_wage for employee: {employee_id}")
            overtime[employee_id] += record.overtime_hours
            late_night[employee_id] += record.late_night_hours
            holiday[employee_id] += record.holiday_hours

        employees: list[EmployeeOvertimePay] = []
        total_premium = Decimal("0")
        exceeding_employee_ids: list[str] = []

        for employee_id in order:
            monthly_overtime = overtime[employee_id]
            within_60 = min(monthly_overtime, OVERTIME_MONTHLY_THRESHOLD)
            over_60 = max(monthly_overtime - OVERTIME_MONTHLY_THRESHOLD, Decimal("0"))
            pay = OvertimePayService.compute(
                hourly_wage=wages[employee_id],
                overtime_hours=within_60,
                overtime_over_60_hours=over_60,
                late_night_hours=late_night[employee_id],
                holiday_hours=holiday[employee_id],
            )
            exceeds = monthly_overtime > OVERTIME_MONTHLY_WARNING
            if exceeds:
                exceeding_employee_ids.append(employee_id)
            employees.append(
                EmployeeOvertimePay(
                    employee_id=employee_id,
                    hourly_wage=wages[employee_id],
                    overtime_hours=monthly_overtime,
                    overtime_within_60_hours=within_60,
                    overtime_over_60_hours=over_60,
                    late_night_hours=late_night[employee_id],
                    holiday_hours=holiday[employee_id],
                    overtime_pay=pay.overtime_pay,
                    overtime_over_60_pay=pay.overtime_over_60_pay,
                    late_night_pay=pay.late_night_pay,
                    holiday_pay=pay.holiday_pay,
                    total_premium=pay.total_premium,
                    exceeds_45_hours=exceeds,
                )
            )
            total_premium += pay.total_premium

        return AttendanceImportResult(
            row_count=len(records),
            employee_count=len(order),
            employees=employees,
            total_premium=total_premium,
            exceeding_employee_ids=exceeding_employee_ids,
        )
