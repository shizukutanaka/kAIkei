from datetime import date
from decimal import Decimal

import pytest

from app.schemas.schemas import BonusImportResponse
from app.services.bonus_import import BonusImportService

# 1: 年度2回で健保の年度累計573万上限に到達 / 2: 同一月2回で厚年の月150万上限に到達
BASIC_CSV = (
    "被保険者整理番号,氏名,支給年月日,賞与額\n"
    "1,山田太郎,2025-07-10,3000000\n"
    "1,山田太郎,2025-12-10,3000000\n"
    "2,佐藤花子,2025-07-10,1000000\n"
    "2,佐藤花子,2025-07-25,800000\n"
)


def test_fiscal_ytd_cap_accumulates_across_payments():
    rows = BonusImportService.parse_csv(BASIC_CSV)
    result = BonusImportService.compute(rows, fiscal_year=2025)

    assert result.payment_count == 4
    assert result.employee_count == 2

    first, second = result.payments[0], result.payments[1]
    assert first.standard_bonus == Decimal("3000000")
    assert first.health_standard_bonus == Decimal("3000000")
    assert first.health_capped is False
    # 厚年は同一月150万が上限
    assert first.pension_standard_bonus == Decimal("1500000")
    assert first.pension_capped is True

    # 2回目は年度累計 300万を引き継ぎ、健保の残枠 5,730,000 − 3,000,000 = 2,730,000
    assert second.fiscal_ytd_standard_bonus == Decimal("3000000")
    assert second.health_standard_bonus == Decimal("2730000")
    assert second.health_capped is True
    # 別月なので厚年は再び150万まで
    assert second.same_month_prior_standard_bonus == Decimal("0")
    assert second.pension_standard_bonus == Decimal("1500000")

    assert result.capped_numbers == ["1", "2"]


def test_same_month_pension_cap_accumulates():
    rows = BonusImportService.parse_csv(BASIC_CSV)
    result = BonusImportService.compute(rows, fiscal_year=2025)

    third, fourth = result.payments[2], result.payments[3]
    assert third.pension_standard_bonus == Decimal("1000000")
    assert third.pension_capped is False
    # 同一月内で既に100万 → 残枠50万
    assert fourth.same_month_prior_standard_bonus == Decimal("1000000")
    assert fourth.pension_standard_bonus == Decimal("500000")
    assert fourth.pension_capped is True
    # 健保は年度累計100万に対し余裕があるため全額
    assert fourth.health_standard_bonus == Decimal("800000")


def test_totals_reflect_capped_amounts():
    rows = BonusImportService.parse_csv(BASIC_CSV)
    result = BonusImportService.compute(rows, fiscal_year=2025)
    assert result.total_bonus_amount == Decimal("7800000")
    # 3,000,000 + 2,730,000 + 1,000,000 + 800,000
    assert result.total_health_standard_bonus == Decimal("7530000")
    # 1,500,000 + 1,500,000 + 1,000,000 + 500,000
    assert result.total_pension_standard_bonus == Decimal("4500000")


def test_standard_bonus_floors_to_1000():
    rows = BonusImportService.parse_csv(
        "被保険者整理番号,氏名,支給年月日,賞与額\n1,A,2025-07-10,\"¥1,234,567\"\n"
    )
    result = BonusImportService.compute(rows, fiscal_year=2025)
    assert result.payments[0].bonus_amount == Decimal("1234567")
    assert result.payments[0].standard_bonus == Decimal("1234000")
    assert result.payments[0].health_standard_bonus == Decimal("1234000")


def test_payments_are_processed_in_date_order_regardless_of_row_order():
    csv_text = (
        "被保険者整理番号,氏名,支給年月日,賞与額\n"
        "1,A,2025-12-10,3000000\n"
        "1,A,2025-07-10,3000000\n"
    )
    result = BonusImportService.compute(
        BonusImportService.parse_csv(csv_text), fiscal_year=2025
    )
    assert [payment.payment_date for payment in result.payments] == [
        date(2025, 7, 10),
        date(2025, 12, 10),
    ]
    assert result.payments[1].health_standard_bonus == Decimal("2730000")


def test_opening_ytd_carry_in_reduces_health_room():
    csv_text = (
        "被保険者整理番号,氏名,支給年月日,賞与額,期首累計標準賞与額\n"
        "1,A,2025-07-10,1000000,5000000\n"
    )
    result = BonusImportService.compute(
        BonusImportService.parse_csv(csv_text), fiscal_year=2025
    )
    # 残枠 5,730,000 − 5,000,000 = 730,000
    assert result.payments[0].health_standard_bonus == Decimal("730000")
    assert result.payments[0].health_capped is True


def test_no_cap_case_has_empty_capped_numbers():
    csv_text = "被保険者整理番号,氏名,支給年月日,賞与額\n1,A,2025-07-10,500000\n"
    result = BonusImportService.compute(
        BonusImportService.parse_csv(csv_text), fiscal_year=2025
    )
    assert result.capped_numbers == []
    assert result.payments[0].health_capped is False
    assert result.payments[0].pension_capped is False


def test_response_schema_validates_result():
    rows = BonusImportService.parse_csv(BASIC_CSV)
    result = BonusImportService.compute(rows, fiscal_year=2025)
    response = BonusImportResponse.model_validate(result)
    assert response.payments[1].health_standard_bonus == Decimal("2730000")
    assert response.csv_text.splitlines()[0].startswith("insured_number,name,payment_date")


def test_fiscal_year_boundaries_are_inclusive():
    csv_text = (
        "被保険者整理番号,氏名,支給年月日,賞与額\n"
        "1,A,2025-04-01,100000\n"
        "1,A,2026-03-31,100000\n"
    )
    result = BonusImportService.compute(
        BonusImportService.parse_csv(csv_text), fiscal_year=2025
    )
    assert result.payment_count == 2


def test_payment_outside_fiscal_year_raises():
    csv_text = "被保険者整理番号,氏名,支給年月日,賞与額\n1,A,2025-03-31,100000\n"
    rows = BonusImportService.parse_csv(csv_text)
    with pytest.raises(ValueError, match="outside fiscal year 2025"):
        BonusImportService.compute(rows, fiscal_year=2025)


def test_slash_payment_date_and_custom_column_map():
    csv_text = "code,nm,pay_date,amount\n1,A,2025/07/10,1000000\n"
    column_map = {
        "insured_number": "code",
        "name": "nm",
        "payment_date": "pay_date",
        "bonus_amount": "amount",
    }
    rows = BonusImportService.parse_csv(csv_text, column_map)
    assert rows[0].payment_date == date(2025, 7, 10)
    assert rows[0].bonus_amount == Decimal("1000000")


def test_invalid_payment_date_raises():
    with pytest.raises(ValueError, match="invalid payment_date value"):
        BonusImportService.parse_csv(
            "被保険者整理番号,氏名,支給年月日,賞与額\n1,A,2025-13-01,100000\n"
        )


def test_negative_bonus_raises():
    with pytest.raises(ValueError, match="bonus_amount must not be negative"):
        BonusImportService.parse_csv(
            "被保険者整理番号,氏名,支給年月日,賞与額\n1,A,2025-07-10,-1\n"
        )


def test_missing_required_column_raises():
    with pytest.raises(ValueError, match="bonus_amount column not found"):
        BonusImportService.parse_csv("被保険者整理番号,氏名,支給年月日\n1,A,2025-07-10\n")


def test_empty_rows_raises():
    with pytest.raises(ValueError, match="must not be empty"):
        BonusImportService.compute([], fiscal_year=2025)


def test_no_header_raises():
    with pytest.raises(ValueError, match="no header row"):
        BonusImportService.parse_csv("")
