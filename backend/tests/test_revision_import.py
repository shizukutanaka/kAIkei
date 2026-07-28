from decimal import Decimal

import pytest

from app.schemas.schemas import RevisionImportResponse
from app.services.revision_import import RevisionImportService

# 1: 3要件充足 / 2: 固定的賃金の変動なし / 3: 支払基礎日数不足 / 4: 2等級差未満
BASIC_CSV = (
    "被保険者整理番号,氏名,支払月,支払基礎日数,通貨支給,現物支給,従前健保標準報酬,従前厚年標準報酬,固定的賃金変動\n"
    "1,山田太郎,4,30,300000,0,240000,240000,1\n"
    "1,山田太郎,5,31,300000,0,240000,240000,1\n"
    "1,山田太郎,6,30,300000,0,240000,240000,1\n"
    "2,佐藤花子,4,30,300000,0,240000,240000,0\n"
    "2,佐藤花子,5,31,300000,0,240000,240000,0\n"
    "2,佐藤花子,6,30,300000,0,240000,240000,0\n"
    "3,鈴木一郎,4,16,300000,0,240000,240000,有\n"
    "3,鈴木一郎,5,31,300000,0,240000,240000,有\n"
    "3,鈴木一郎,6,30,300000,0,240000,240000,有\n"
    "4,田中次郎,4,30,310000,0,300000,300000,有\n"
    "4,田中次郎,5,31,310000,0,300000,300000,有\n"
    "4,田中次郎,6,30,310000,0,300000,300000,有\n"
)


def test_eligible_employee_is_flagged():
    rows = RevisionImportService.parse_csv(BASIC_CSV)
    result = RevisionImportService.compute(rows, start_year=2025)

    assert result.row_count == 12
    assert result.employee_count == 4

    e1 = result.employees[0]
    assert e1.month_totals == [Decimal("300000")] * 3
    assert e1.average == Decimal("300000")
    # 従前240,000 は健保19等級、300,000 は健保22等級 → 3等級差
    assert (e1.prev_health_grade, e1.new_health_grade, e1.health_grade_diff) == (19, 22, 3)
    assert (e1.prev_pension_grade, e1.new_pension_grade) == (16, 19)
    assert e1.new_health_standard == Decimal("300000")
    assert e1.days_ok is True
    assert e1.revision_required is True
    assert e1.reason == "eligible"
    # 4月起算 → 4か月目の7月改定
    assert (e1.start_month, e1.revision_year_month) == (4, "2025-07")


def test_fixed_wage_not_changed_is_not_eligible():
    rows = RevisionImportService.parse_csv(BASIC_CSV)
    result = RevisionImportService.compute(rows, start_year=2025)
    e2 = result.employees[1]
    # 等級差は同じ3等級だが固定的賃金の変動が無いため対象外
    assert e2.health_grade_diff == 3
    assert e2.revision_required is False
    assert e2.reason == "fixed_wage_not_changed"


def test_insufficient_payment_basis_days_is_not_eligible():
    rows = RevisionImportService.parse_csv(BASIC_CSV)
    result = RevisionImportService.compute(rows, start_year=2025)
    e3 = result.employees[2]
    # 随時改定は3か月すべて17日以上が必要(算定基礎届と異なり平均を出さない)
    assert e3.days_ok is False
    assert e3.average is None
    assert e3.new_health_grade is None
    assert e3.revision_required is False
    assert e3.reason == "insufficient_days"


def test_grade_diff_below_2_is_not_eligible():
    rows = RevisionImportService.parse_csv(BASIC_CSV)
    result = RevisionImportService.compute(rows, start_year=2025)
    e4 = result.employees[3]
    # 従前300,000(22等級) → 310,000(23等級) の1等級差
    assert (e4.prev_health_grade, e4.new_health_grade, e4.health_grade_diff) == (22, 23, 1)
    assert e4.revision_required is False
    assert e4.reason == "grade_diff_below_2"


def test_only_eligible_numbers_are_listed():
    rows = RevisionImportService.parse_csv(BASIC_CSV)
    result = RevisionImportService.compute(rows, start_year=2025)
    assert result.revision_required_numbers == ["1"]


def test_response_schema_validates_result():
    rows = RevisionImportService.parse_csv(BASIC_CSV)
    result = RevisionImportService.compute(rows, start_year=2025)
    response = RevisionImportResponse.model_validate(result)
    assert response.employees[0].revision_required is True
    assert response.employees[2].average is None
    assert response.csv_text.splitlines()[0].startswith("insured_number,name,fixed_wage_changed")


def test_year_wrapping_revision_month():
    csv_text = (
        "被保険者整理番号,氏名,支払月,支払基礎日数,通貨支給,従前健保標準報酬,従前厚年標準報酬,固定的賃金変動\n"
        "1,A,12,30,300000,240000,240000,1\n"
        "1,A,1,31,300000,240000,240000,1\n"
        "1,A,2,28,300000,240000,240000,1\n"
    )
    rows = RevisionImportService.parse_csv(csv_text)
    result = RevisionImportService.compute(rows, start_year=2025)
    # 12月起算のため 1・2月は翌年、改定は翌年3月
    assert (result.employees[0].start_month, result.employees[0].revision_year_month) == (12, "2026-03")


def test_in_kind_remuneration_is_included():
    csv_text = (
        "被保険者整理番号,氏名,支払月,支払基礎日数,通貨支給,現物支給,従前健保標準報酬,従前厚年標準報酬,固定的賃金変動\n"
        "1,A,4,30,295000,5000,240000,240000,1\n"
        "1,A,5,31,300000,0,240000,240000,1\n"
        "1,A,6,30,300000,0,240000,240000,1\n"
    )
    rows = RevisionImportService.parse_csv(csv_text)
    result = RevisionImportService.compute(rows, start_year=2025)
    assert result.employees[0].month_totals[0] == Decimal("300000")
    assert result.employees[0].average == Decimal("300000")


def test_custom_column_map_and_amount_tokens():
    csv_text = "code,nm,m,days,pay,prev_h,prev_p,changed\n1,A,4,30,\"¥300,000\",240000,240000,あり\n"
    column_map = {
        "insured_number": "code",
        "name": "nm",
        "month": "m",
        "payment_basis_days": "days",
        "currency_remuneration": "pay",
        "previous_health_standard": "prev_h",
        "previous_pension_standard": "prev_p",
        "fixed_wage_changed": "changed",
    }
    rows = RevisionImportService.parse_csv(csv_text, column_map)
    assert rows[0].currency_remuneration == Decimal("300000")
    assert rows[0].fixed_wage_changed is True


def test_non_consecutive_months_raise():
    csv_text = (
        "被保険者整理番号,氏名,支払月,支払基礎日数,通貨支給,従前健保標準報酬,従前厚年標準報酬,固定的賃金変動\n"
        "1,A,4,30,300000,240000,240000,1\n"
        "1,A,5,31,300000,240000,240000,1\n"
        "1,A,8,30,300000,240000,240000,1\n"
    )
    rows = RevisionImportService.parse_csv(csv_text)
    with pytest.raises(ValueError, match="3 consecutive months"):
        RevisionImportService.compute(rows, start_year=2025)


def test_wrong_month_count_raises():
    csv_text = (
        "被保険者整理番号,氏名,支払月,支払基礎日数,通貨支給,従前健保標準報酬,従前厚年標準報酬,固定的賃金変動\n"
        "1,A,4,30,300000,240000,240000,1\n"
        "1,A,5,31,300000,240000,240000,1\n"
    )
    rows = RevisionImportService.parse_csv(csv_text)
    with pytest.raises(ValueError, match="must have exactly 3 months, got 2"):
        RevisionImportService.compute(rows, start_year=2025)


def test_duplicate_month_raises():
    csv_text = (
        "被保険者整理番号,氏名,支払月,支払基礎日数,通貨支給,従前健保標準報酬,従前厚年標準報酬,固定的賃金変動\n"
        "1,A,4,30,300000,240000,240000,1\n"
        "1,A,4,30,300000,240000,240000,1\n"
        "1,A,5,31,300000,240000,240000,1\n"
    )
    rows = RevisionImportService.parse_csv(csv_text)
    with pytest.raises(ValueError, match="duplicate month 4"):
        RevisionImportService.compute(rows, start_year=2025)


def test_month_out_of_range_raises():
    with pytest.raises(ValueError, match="month must be between 1 and 12"):
        RevisionImportService.parse_csv(
            "被保険者整理番号,氏名,支払月,支払基礎日数,通貨支給,固定的賃金変動\n1,A,13,30,300000,1\n"
        )


def test_invalid_fixed_wage_flag_raises():
    with pytest.raises(ValueError, match="invalid fixed_wage_changed value"):
        RevisionImportService.parse_csv(
            "被保険者整理番号,氏名,支払月,支払基礎日数,通貨支給,固定的賃金変動\n1,A,4,30,300000,maybe\n"
        )


def test_missing_required_column_raises():
    with pytest.raises(ValueError, match="payment_basis_days column not found"):
        RevisionImportService.parse_csv("被保険者整理番号,氏名,支払月,通貨支給\n1,A,4,300000\n")


def test_empty_rows_raises():
    with pytest.raises(ValueError, match="must not be empty"):
        RevisionImportService.compute([], start_year=2025)


def test_no_header_raises():
    with pytest.raises(ValueError, match="no header row"):
        RevisionImportService.parse_csv("")
