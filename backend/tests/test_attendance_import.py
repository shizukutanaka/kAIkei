from decimal import Decimal

import pytest

from app.schemas.schemas import AttendanceImportResponse
from app.services.attendance_import import AttendanceImportService, AttendanceRecord

# A は月次2行で時間外70時間(40+30)。行ごとに60時間判定すると割増率が上がらず過少計算になる。
BASIC_CSV = (
    "社員番号,時給,時間外,深夜,休日\n"
    "A,2000,40,10,8\n"
    "A,2000,30,0,0\n"
    "B,1500,20,0,0\n"
)


def test_monthly_aggregation_splits_overtime_at_60_hours():
    records = AttendanceImportService.parse_csv(BASIC_CSV)
    result = AttendanceImportService.compute(records)

    assert result.row_count == 3
    assert result.employee_count == 2

    a = result.employees[0]
    assert a.employee_id == "A"
    assert a.overtime_hours == Decimal("70")
    assert a.overtime_within_60_hours == Decimal("60")
    assert a.overtime_over_60_hours == Decimal("10")
    # 2000 × 60 × 1.25
    assert a.overtime_pay == Decimal("150000")
    # 2000 × 10 × 1.50 (月60時間超)
    assert a.overtime_over_60_pay == Decimal("30000")
    # 2000 × 10 × 0.25 (深夜割増は加算分のみ)
    assert a.late_night_pay == Decimal("5000")
    # 2000 × 8 × 1.35
    assert a.holiday_pay == Decimal("21600")
    assert a.total_premium == Decimal("206600")
    assert a.exceeds_45_hours is True

    b = result.employees[1]
    assert b.employee_id == "B"
    assert b.overtime_within_60_hours == Decimal("20")
    assert b.overtime_over_60_hours == Decimal("0")
    assert b.overtime_pay == Decimal("37500")
    assert b.total_premium == Decimal("37500")
    assert b.exceeds_45_hours is False

    assert result.total_premium == Decimal("244100")
    assert result.exceeding_employee_ids == ["A"]


def test_per_row_split_would_undercount():
    """月次合算前に60時間判定すると 175,000 + 0 になり、正しい 150,000 + 30,000 と一致しない。"""
    records = AttendanceImportService.parse_csv(BASIC_CSV)
    result = AttendanceImportService.compute(records)
    a = result.employees[0]
    assert a.overtime_pay + a.overtime_over_60_pay == Decimal("180000")
    assert a.overtime_pay + a.overtime_over_60_pay != Decimal("175000")


def test_response_schema_validates_result():
    records = AttendanceImportService.parse_csv(BASIC_CSV)
    result = AttendanceImportService.compute(records)
    response = AttendanceImportResponse.model_validate(result)
    assert response.total_premium == Decimal("244100")
    assert response.employees[0].employee_id == "A"


def test_exactly_45_hours_is_not_flagged():
    records = AttendanceImportService.parse_csv("社員番号,時給,時間外\nA,2000,45\n")
    result = AttendanceImportService.compute(records)
    assert result.employees[0].exceeds_45_hours is False
    assert result.exceeding_employee_ids == []


def test_just_over_45_hours_is_flagged():
    records = AttendanceImportService.parse_csv("社員番号,時給,時間外\nA,2000,45.5\n")
    result = AttendanceImportService.compute(records)
    assert result.employees[0].exceeds_45_hours is True
    assert result.exceeding_employee_ids == ["A"]


def test_exactly_60_hours_has_no_over_60_portion():
    records = AttendanceImportService.parse_csv("社員番号,時給,時間外\nA,2000,60\n")
    result = AttendanceImportService.compute(records)
    assert result.employees[0].overtime_within_60_hours == Decimal("60")
    assert result.employees[0].overtime_over_60_hours == Decimal("0")
    assert result.employees[0].overtime_over_60_pay == Decimal("0")


def test_fractional_hours_and_rounding_down():
    # 1,530 × 1.5h × 1.25 = 2,868.75 -> 円未満切捨で 2,868
    records = AttendanceImportService.parse_csv("社員番号,時給,時間外\nA,1530,1.5\n")
    result = AttendanceImportService.compute(records)
    assert result.employees[0].overtime_pay == Decimal("2868")


def test_missing_hour_columns_default_to_zero():
    records = AttendanceImportService.parse_csv("社員番号,時給\nA,2000\n")
    result = AttendanceImportService.compute(records)
    assert result.employees[0].overtime_hours == Decimal("0")
    assert result.employees[0].total_premium == Decimal("0")


def test_custom_column_map():
    csv_text = "code,rate,ot,night,hol\nA,2000,10,2,0\n"
    column_map = {
        "employee_id": "code",
        "hourly_wage": "rate",
        "overtime_hours": "ot",
        "late_night_hours": "night",
        "holiday_hours": "hol",
    }
    records = AttendanceImportService.parse_csv(csv_text, column_map)
    assert records == [
        AttendanceRecord(
            employee_id="A",
            hourly_wage=Decimal("2000"),
            overtime_hours=Decimal("10"),
            late_night_hours=Decimal("2"),
            holiday_hours=Decimal("0"),
        )
    ]


def test_inconsistent_hourly_wage_raises():
    csv_text = "社員番号,時給,時間外\nA,2000,10\nA,2100,10\n"
    records = AttendanceImportService.parse_csv(csv_text)
    with pytest.raises(ValueError, match="inconsistent hourly_wage"):
        AttendanceImportService.compute(records)


def test_missing_hourly_wage_column_raises():
    with pytest.raises(ValueError, match="hourly_wage column not found"):
        AttendanceImportService.parse_csv("社員番号,時間外\nA,10\n")


def test_negative_hours_raise():
    with pytest.raises(ValueError, match="overtime_hours must not be negative"):
        AttendanceImportService.parse_csv("社員番号,時給,時間外\nA,2000,-1\n")


def test_empty_records_raises():
    with pytest.raises(ValueError, match="must not be empty"):
        AttendanceImportService.compute([])


def test_no_header_raises():
    with pytest.raises(ValueError, match="no header row"):
        AttendanceImportService.parse_csv("")
