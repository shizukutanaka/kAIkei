from datetime import date

import pytest

from app.schemas.schemas import PayrollCloseResponse
from app.services.payroll_close import (
    FORM_ATTENDANCE,
    FORM_BONUS,
    FORM_LABOR_INSURANCE,
    FORM_MONTHLY_REVISION,
    FORM_SANTEI,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_MISSING_INPUT,
    STATUS_NOT_REQUIRED,
    PayrollCloseInput,
    PayrollCloseService,
)

ATTENDANCE_CSV = (
    "社員番号,時給,時間外,深夜,休日\n"
    "E1,2000,40,0,0\n"
    "E1,2000,30,10,8\n"
    "E2,1500,10,0,0\n"
)

SANTEI_CSV = (
    "被保険者整理番号,氏名,生年月日,支払月,支払基礎日数,通貨支給,現物支給,従前健保標準報酬,従前厚年標準報酬\n"
    "1,山田太郎,1985-04-01,4,30,300000,0,300000,300000\n"
    "1,山田太郎,1985-04-01,5,31,310000,0,300000,300000\n"
    "1,山田太郎,1985-04-01,6,30,320000,0,300000,300000\n"
)

LABOR_CSV = "社員番号,賃金,雇用保険対象\nE1,3000000,1\nE2,3000000,1\n"

BONUS_CSV = "被保険者整理番号,氏名,支給年月日,賞与額\n1,山田太郎,2025-07-10,1000000\n"

REVISION_CSV = (
    "被保険者整理番号,氏名,支払月,支払基礎日数,通貨支給,現物支給,従前健保標準報酬,従前厚年標準報酬,固定的賃金変動\n"
    "1,山田太郎,4,30,300000,0,240000,240000,1\n"
    "1,山田太郎,5,31,300000,0,240000,240000,0\n"
    "1,山田太郎,6,30,300000,0,240000,240000,0\n"
)


def _outcome(result, form):
    return next(outcome for outcome in result.outcomes if outcome.form == form)


def test_july_requires_santei_and_attendance():
    result = PayrollCloseService.run(
        PayrollCloseInput(
            fiscal_year=2025,
            target_month=7,
            attendance_csv=ATTENDANCE_CSV,
            santei_csv=SANTEI_CSV,
        ),
    )

    assert _outcome(result, FORM_SANTEI).required is True
    assert _outcome(result, FORM_SANTEI).status == STATUS_COMPLETED
    assert _outcome(result, FORM_ATTENDANCE).status == STATUS_COMPLETED
    assert _outcome(result, FORM_LABOR_INSURANCE).status == STATUS_NOT_REQUIRED
    assert result.close_ready is True
    assert result.blocking_forms == []


def test_june_requires_labor_insurance_annual_update():
    result = PayrollCloseService.run(
        PayrollCloseInput(
            fiscal_year=2025,
            target_month=6,
            attendance_csv=ATTENDANCE_CSV,
            labor_insurance_csv=LABOR_CSV,
        ),
    )

    labor = _outcome(result, FORM_LABOR_INSURANCE)
    assert labor.required is True
    assert labor.status == STATUS_COMPLETED
    assert labor.summary["workers_comp_premium"] == "18000"
    assert labor.summary["employment_premium"] == "93000"
    assert labor.summary["determined_premium"] == "111000"
    assert _outcome(result, FORM_SANTEI).status == STATUS_NOT_REQUIRED
    assert result.close_ready is True


def test_missing_required_input_blocks_close():
    result = PayrollCloseService.run(
        PayrollCloseInput(
            fiscal_year=2025,
            target_month=7,
            attendance_csv=ATTENDANCE_CSV,
        ),
    )

    assert _outcome(result, FORM_SANTEI).status == STATUS_MISSING_INPUT
    assert result.blocking_forms == [FORM_SANTEI]
    assert result.close_ready is False


def test_missing_attendance_blocks_every_month():
    result = PayrollCloseService.run(
        PayrollCloseInput(fiscal_year=2025, target_month=9, bonus_csv=BONUS_CSV),
    )

    assert _outcome(result, FORM_ATTENDANCE).status == STATUS_MISSING_INPUT
    assert result.blocking_forms == [FORM_ATTENDANCE]
    assert _outcome(result, FORM_BONUS).status == STATUS_COMPLETED
    assert result.close_ready is False


def test_one_broken_csv_does_not_stop_other_forms():
    result = PayrollCloseService.run(
        PayrollCloseInput(
            fiscal_year=2025,
            target_month=7,
            attendance_csv=ATTENDANCE_CSV,
            santei_csv=SANTEI_CSV,
            bonus_csv="被保険者整理番号,氏名,支給年月日\n1,山田太郎,2025-07-10\n",
        ),
    )

    bonus = _outcome(result, FORM_BONUS)
    assert bonus.status == STATUS_FAILED
    assert "bonus_amount column not found" in bonus.detail
    assert result.failed_forms == [FORM_BONUS]
    assert _outcome(result, FORM_SANTEI).status == STATUS_COMPLETED
    assert _outcome(result, FORM_ATTENDANCE).status == STATUS_COMPLETED
    # 賞与支払届は事象ベースで暦上の必須ではないため締めは止めない
    assert result.blocking_forms == []
    assert result.close_ready is True


def test_failed_required_form_blocks_close():
    result = PayrollCloseService.run(
        PayrollCloseInput(
            fiscal_year=2025,
            target_month=7,
            attendance_csv=ATTENDANCE_CSV,
            santei_csv="被保険者整理番号,氏名\n1,山田太郎\n",
        ),
    )

    assert _outcome(result, FORM_SANTEI).status == STATUS_FAILED
    assert result.blocking_forms == [FORM_SANTEI]
    assert result.close_ready is False


def test_event_based_forms_run_when_provided():
    result = PayrollCloseService.run(
        PayrollCloseInput(
            fiscal_year=2025,
            target_month=8,
            attendance_csv=ATTENDANCE_CSV,
            revision_csv=REVISION_CSV,
            bonus_csv=BONUS_CSV,
        ),
    )

    revision = _outcome(result, FORM_MONTHLY_REVISION)
    assert revision.required is False
    assert revision.status == STATUS_COMPLETED
    assert revision.summary["revision_required_count"] == "1"
    assert revision.csv_text is not None
    assert _outcome(result, FORM_BONUS).summary["payment_count"] == "1"


def test_attendance_summary_aggregates_hours_before_rate_switch():
    result = PayrollCloseService.run(
        PayrollCloseInput(fiscal_year=2025, target_month=9, attendance_csv=ATTENDANCE_CSV),
    )

    attendance = _outcome(result, FORM_ATTENDANCE)
    # E1: 70h → 60h×2000×1.25 + 10h×2000×1.50 + 深夜10h×2000×0.25 + 休日8h×2000×1.35
    #   = 150,000 + 30,000 + 5,000 + 21,600 = 206,600 / E2: 10h×1500×1.25 = 18,750
    assert attendance.summary["total_premium"] == "225350"
    assert attendance.summary["exceeding_45_hours_count"] == "1"


def test_statutory_deadlines_exposed():
    result = PayrollCloseService.run(
        PayrollCloseInput(
            fiscal_year=2025,
            target_month=7,
            attendance_csv=ATTENDANCE_CSV,
            santei_csv=SANTEI_CSV,
        ),
    )

    assert _outcome(result, FORM_SANTEI).statutory_deadline == date(2025, 7, 10)
    assert _outcome(result, FORM_LABOR_INSURANCE).statutory_deadline == date(2025, 7, 10)
    assert _outcome(result, FORM_ATTENDANCE).statutory_deadline is None


def test_column_maps_are_routed_per_form():
    result = PayrollCloseService.run(
        PayrollCloseInput(
            fiscal_year=2025,
            target_month=9,
            attendance_csv="ID,単価,時間外,深夜,休日\nE1,2000,10,0,0\n",
            column_maps={FORM_ATTENDANCE: {"employee_id": "ID", "hourly_wage": "単価"}},
        ),
    )

    assert _outcome(result, FORM_ATTENDANCE).status == STATUS_COMPLETED
    assert _outcome(result, FORM_ATTENDANCE).summary["total_premium"] == "25000"


def test_response_schema_validates_service_result():
    result = PayrollCloseService.run(
        PayrollCloseInput(fiscal_year=2025, target_month=9, attendance_csv=ATTENDANCE_CSV),
    )

    response = PayrollCloseResponse.model_validate(result)

    assert response.target_month == 9
    assert response.outcomes[0].form == FORM_ATTENDANCE


def test_invalid_month_rejected():
    with pytest.raises(ValueError, match="target_month"):
        PayrollCloseService.run(
            PayrollCloseInput(fiscal_year=2025, target_month=13, attendance_csv=ATTENDANCE_CSV),
        )


def test_no_csv_input_rejected():
    with pytest.raises(ValueError, match="at least one csv"):
        PayrollCloseService.run(PayrollCloseInput(fiscal_year=2025, target_month=9))


def test_blank_csv_counts_as_missing():
    with pytest.raises(ValueError, match="at least one csv"):
        PayrollCloseService.run(
            PayrollCloseInput(fiscal_year=2025, target_month=9, attendance_csv="   \n"),
        )
