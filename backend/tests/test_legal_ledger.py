import pytest

from app.services.legal_ledger import (
    ATTENDANCE_RECORD_FIELDS,
    WAGE_LEDGER_FIELDS,
    WORKER_ROSTER_FIELDS,
    LegalLedgerService,
)


def test_wage_ledger_complete():
    result = LegalLedgerService.check("wage_ledger", list(WAGE_LEDGER_FIELDS))
    assert result.compliant is True
    assert result.missing_fields == ()


def test_wage_ledger_missing():
    present = [f for f in WAGE_LEDGER_FIELDS if f not in ("overtime_hours", "deduction_items")]
    result = LegalLedgerService.check("wage_ledger", present)
    assert result.compliant is False
    assert set(result.missing_fields) == {"overtime_hours", "deduction_items"}


def test_worker_roster_complete():
    result = LegalLedgerService.check("worker_roster", list(WORKER_ROSTER_FIELDS))
    assert result.compliant is True


def test_attendance_record_missing():
    result = LegalLedgerService.check("attendance_record", ["name", "work_days"])
    assert result.compliant is False
    assert "start_end_times" in result.missing_fields


def test_extra_fields_ignored():
    result = LegalLedgerService.check("attendance_record", list(ATTENDANCE_RECORD_FIELDS) + ["memo"])
    assert result.compliant is True


def test_unsupported_ledger_type_raises():
    with pytest.raises(ValueError):
        LegalLedgerService.check("tax_ledger", [])
