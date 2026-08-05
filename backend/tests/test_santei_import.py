from datetime import date
from decimal import Decimal

import pytest

from app.schemas.schemas import SanteiImportResponse
from app.services.santei_import import SanteiImportService

# E1: 3か月すべて17日以上 / E2: 4月が10日で算定対象外 / E3: 全月17日未満で保険者算定が必要
BASIC_CSV = (
    "被保険者整理番号,氏名,生年月日,支払月,支払基礎日数,通貨支給,現物支給,従前健保標準報酬,従前厚年標準報酬\n"
    "1,山田太郎,1985-04-01,4,30,295000,5000,300000,300000\n"
    "1,山田太郎,1985-04-01,5,31,320000,0,300000,300000\n"
    "1,山田太郎,1985-04-01,6,30,310000,0,300000,300000\n"
    "2,佐藤花子,1990-08-15,4,10,80000,0,200000,200000\n"
    "2,佐藤花子,1990-08-15,5,30,200000,0,200000,200000\n"
    "2,佐藤花子,1990-08-15,6,30,210000,0,200000,200000\n"
    "3,鈴木一郎,1978-01-20,4,10,80000,0,98000,98000\n"
    "3,鈴木一郎,1978-01-20,5,12,90000,0,98000,98000\n"
)


def test_basic_santei_generation():
    rows = SanteiImportService.parse_csv(BASIC_CSV)
    result = SanteiImportService.compute(rows, applicable_year=2025)

    assert result.row_count == 8
    assert result.employee_count == 3

    e1 = result.employees[0]
    # 現物支給を含めて月額を算定 (295,000 + 5,000)
    assert e1.month_totals == [Decimal("300000"), Decimal("320000"), Decimal("310000")]
    assert e1.total == Decimal("930000")
    assert e1.average == Decimal("310000")
    # 310,000 は健保23等級(310,000〜330,000未満)・厚年20等級
    assert (e1.health_grade, e1.health_standard) == (23, Decimal("320000"))
    assert (e1.pension_grade, e1.pension_standard) == (20, Decimal("320000"))
    assert e1.requires_manual is False


def test_months_below_17_days_are_excluded_from_average():
    rows = SanteiImportService.parse_csv(BASIC_CSV)
    result = SanteiImportService.compute(rows, applicable_year=2025)

    e2 = result.employees[1]
    # 4月(10日)を除外し (200,000 + 210,000) ÷ 2
    assert e2.total == Decimal("410000")
    assert e2.average == Decimal("205000")
    assert (e2.health_grade, e2.health_standard) == (17, Decimal("200000"))
    assert (e2.pension_grade, e2.pension_standard) == (14, Decimal("200000"))
    # 3か月平均 (80,000+200,000+210,000)÷3 = 163,333 とは一致しない
    assert e2.average != Decimal("163333")


def test_no_qualifying_month_requires_manual_determination():
    rows = SanteiImportService.parse_csv(BASIC_CSV)
    result = SanteiImportService.compute(rows, applicable_year=2025)

    e3 = result.employees[2]
    assert e3.average is None
    assert e3.health_grade is None
    assert e3.pension_grade is None
    assert e3.requires_manual is True
    assert result.manual_review_numbers == ["3"]


def test_average_is_floored_to_yen():
    csv_text = (
        "被保険者整理番号,氏名,生年月日,支払月,支払基礎日数,通貨支給\n"
        "1,A,1985-04-01,4,30,300001\n"
        "1,A,1985-04-01,5,30,300001\n"
        "1,A,1985-04-01,6,30,300000\n"
    )
    rows = SanteiImportService.parse_csv(csv_text)
    result = SanteiImportService.compute(rows, applicable_year=2025)
    # 900,002 ÷ 3 = 300,000.666... → 円未満切捨
    assert result.employees[0].average == Decimal("300000")


def test_csv_output_contains_header_and_grades():
    rows = SanteiImportService.parse_csv(BASIC_CSV)
    result = SanteiImportService.compute(rows, applicable_year=2025, applicable_month=9)
    lines = result.csv_text.strip().split("\n")
    assert lines[0].startswith("insured_number,name,birth_date,applicable_ym")
    assert len(lines) == 4
    assert "2025-09" in lines[1]
    assert lines[1].endswith("310000,23,320000,20,320000,False")


def test_response_schema_validates_result():
    rows = SanteiImportService.parse_csv(BASIC_CSV)
    result = SanteiImportService.compute(rows, applicable_year=2025)
    response = SanteiImportResponse.model_validate(result)
    assert response.employees[0].average == Decimal("310000")
    assert response.employees[2].average is None


def test_month_labels_with_suffix_are_accepted():
    csv_text = (
        "被保険者整理番号,氏名,生年月日,支払月,支払基礎日数,通貨支給\n"
        "1,A,1985-04-01,4月,30,300000\n"
        "1,A,1985-04-01,5月,30,300000\n"
    )
    rows = SanteiImportService.parse_csv(csv_text)
    assert [row.month for row in rows] == [4, 5]


def test_slash_birth_date_is_accepted():
    csv_text = (
        "被保険者整理番号,氏名,生年月日,支払月,支払基礎日数,通貨支給\n"
        "1,A,1985/04/01,4,30,300000\n"
    )
    rows = SanteiImportService.parse_csv(csv_text)
    assert rows[0].birth_date == date(1985, 4, 1)


def test_custom_column_map():
    csv_text = "code,nm,dob,m,days,pay\n1,A,1985-04-01,4,30,300000\n"
    column_map = {
        "insured_number": "code",
        "name": "nm",
        "birth_date": "dob",
        "month": "m",
        "payment_basis_days": "days",
        "currency_remuneration": "pay",
    }
    rows = SanteiImportService.parse_csv(csv_text, column_map)
    assert rows[0].insured_number == "1"
    assert rows[0].currency_remuneration == Decimal("300000")
    assert rows[0].in_kind_remuneration == Decimal("0")


def test_month_outside_april_to_june_raises():
    csv_text = (
        "被保険者整理番号,氏名,生年月日,支払月,支払基礎日数,通貨支給\n"
        "1,A,1985-04-01,7,30,300000\n"
    )
    with pytest.raises(ValueError, match=r"month must be one of \[4, 5, 6\]"):
        SanteiImportService.parse_csv(csv_text)


def test_duplicate_month_raises():
    csv_text = (
        "被保険者整理番号,氏名,生年月日,支払月,支払基礎日数,通貨支給\n"
        "1,A,1985-04-01,4,30,300000\n"
        "1,A,1985-04-01,4,30,300000\n"
    )
    rows = SanteiImportService.parse_csv(csv_text)
    with pytest.raises(ValueError, match="duplicate month 4"):
        SanteiImportService.compute(rows, applicable_year=2025)


def test_inconsistent_birth_date_raises():
    csv_text = (
        "被保険者整理番号,氏名,生年月日,支払月,支払基礎日数,通貨支給\n"
        "1,A,1985-04-01,4,30,300000\n"
        "1,A,1985-04-02,5,30,300000\n"
    )
    rows = SanteiImportService.parse_csv(csv_text)
    with pytest.raises(ValueError, match="inconsistent birth_date"):
        SanteiImportService.compute(rows, applicable_year=2025)


def test_missing_required_column_raises():
    with pytest.raises(ValueError, match="birth_date column not found"):
        SanteiImportService.parse_csv(
            "被保険者整理番号,氏名,支払月,支払基礎日数,通貨支給\n1,A,4,30,300000\n"
        )


def test_invalid_birth_date_raises():
    with pytest.raises(ValueError, match="invalid birth_date value"):
        SanteiImportService.parse_csv(
            "被保険者整理番号,氏名,生年月日,支払月,支払基礎日数,通貨支給\n1,A,1985-13-01,4,30,300000\n"
        )


def test_negative_remuneration_raises():
    with pytest.raises(ValueError, match="currency_remuneration must not be negative"):
        SanteiImportService.parse_csv(
            "被保険者整理番号,氏名,生年月日,支払月,支払基礎日数,通貨支給\n1,A,1985-04-01,4,30,-1\n"
        )


def test_empty_rows_raises():
    with pytest.raises(ValueError, match="must not be empty"):
        SanteiImportService.compute([], applicable_year=2025)


def test_no_header_raises():
    with pytest.raises(ValueError, match="no header row"):
        SanteiImportService.parse_csv("")
