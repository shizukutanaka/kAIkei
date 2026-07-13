"""法定帳簿の記載事項チェック。

労働基準法107条(労働者名簿)・108条(賃金台帳)および出勤簿(始業終業時刻の記録:
労働時間の適正把握ガイドライン)で定められた記載事項が揃っているかを検証する。
"""

from __future__ import annotations

from dataclasses import dataclass

LEDGER_WAGE = "wage_ledger"
LEDGER_ROSTER = "worker_roster"
LEDGER_ATTENDANCE = "attendance_record"

# 労基法108条 賃金台帳の記載事項
WAGE_LEDGER_FIELDS: tuple[str, ...] = (
    "name",
    "sex",
    "wage_calc_period",
    "work_days",
    "work_hours",
    "overtime_hours",
    "late_night_hours",
    "holiday_work_hours",
    "wage_items",
    "deduction_items",
)
# 労基法107条 労働者名簿の記載事項
WORKER_ROSTER_FIELDS: tuple[str, ...] = (
    "name",
    "birth_date",
    "history",
    "sex",
    "address",
    "job_type",
    "hire_date",
    "retirement",
    "death",
)
# 出勤簿の記載事項(労働時間の適正把握ガイドライン)
ATTENDANCE_RECORD_FIELDS: tuple[str, ...] = (
    "name",
    "work_days",
    "start_end_times",
    "break_time",
    "overtime_holiday_late_night_hours",
)

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    LEDGER_WAGE: WAGE_LEDGER_FIELDS,
    LEDGER_ROSTER: WORKER_ROSTER_FIELDS,
    LEDGER_ATTENDANCE: ATTENDANCE_RECORD_FIELDS,
}


@dataclass(frozen=True)
class LegalLedgerCheckResult:
    ledger_type: str
    required_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    compliant: bool


class LegalLedgerService:
    @classmethod
    def check(cls, ledger_type: str, present_fields: list[str]) -> LegalLedgerCheckResult:
        required = REQUIRED_FIELDS.get(ledger_type)
        if required is None:
            raise ValueError(f"unsupported ledger_type: {ledger_type}")

        present = set(present_fields)
        missing = tuple(field for field in required if field not in present)
        return LegalLedgerCheckResult(
            ledger_type=ledger_type,
            required_fields=required,
            missing_fields=missing,
            compliant=not missing,
        )
