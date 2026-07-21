from decimal import Decimal

import pytest

from app.schemas.schemas import PayrollWageImportResponse
from app.services.payroll_wage_import import (
    PayrollWageImportService,
    WageRecord,
)

BASIC_CSV = (
    "社員番号,賃金,雇用保険対象,労災対象\n"
    "E1,1500000,1,1\n"
    "E1,1500000,1,1\n"
    "E2,2000000,対象,対象\n"
    "E3,1000000,対象外,対象\n"
)


def test_basic_calculation_general_business():
    records = PayrollWageImportService.parse_csv(BASIC_CSV)
    result = PayrollWageImportService.compute(records, business_type="general")

    assert result.row_count == 4
    assert result.employee_count == 3
    assert result.employment_insured_count == 2
    assert result.workers_comp_wage_total == Decimal("6000000")
    assert result.employment_wage_total == Decimal("5000000")
    assert result.workers_comp_base == Decimal("6000000")
    assert result.employment_base == Decimal("5000000")
    # 労災 6,000,000 × 0.003
    assert result.workers_comp_premium == Decimal("18000")
    # 雇用 被保険者 5,000,000 × 0.006 / 0.0095
    assert result.employment_employee_premium == Decimal("30000")
    assert result.employment_employer_premium == Decimal("47500")
    assert result.employment_premium == Decimal("77500")
    # 一般拠出金 6,000,000 × 0.00002
    assert result.general_contribution == Decimal("120")
    assert result.determined_premium == Decimal("95500")


def test_response_schema_validates_result():
    records = PayrollWageImportService.parse_csv(BASIC_CSV)
    result = PayrollWageImportService.compute(records, business_type="general")
    response = PayrollWageImportResponse.model_validate(result)
    assert response.determined_premium == Decimal("95500")


def test_wage_total_floored_to_1000():
    csv_text = "社員番号,賃金\nE1,1234567\n"
    records = PayrollWageImportService.parse_csv(csv_text)
    result = PayrollWageImportService.compute(records, business_type="general")
    # no insured columns -> everyone insured for both
    assert result.workers_comp_wage_total == Decimal("1234567")
    assert result.workers_comp_base == Decimal("1234000")
    assert result.employment_base == Decimal("1234000")


def test_missing_insured_columns_defaults_to_all_insured():
    csv_text = "社員番号,賃金\nE1,1000000\nE2,2000000\n"
    records = PayrollWageImportService.parse_csv(csv_text)
    result = PayrollWageImportService.compute(records, business_type="general")
    assert result.employment_insured_count == 2
    assert result.employment_wage_total == Decimal("3000000")
    assert result.workers_comp_wage_total == Decimal("3000000")


def test_wage_with_comma_and_yen_sign():
    csv_text = "社員番号,賃金\nE1,\"1,000,000\"\nE2,¥500000\n"
    records = PayrollWageImportService.parse_csv(csv_text)
    result = PayrollWageImportService.compute(records, business_type="general")
    assert result.workers_comp_wage_total == Decimal("1500000")


def test_custom_column_map():
    csv_text = "code,pay,ei,wc\nA,1000000,yes,yes\n"
    column_map = {
        "employee_id": "code",
        "wage": "pay",
        "employment_insured": "ei",
        "workers_comp_insured": "wc",
    }
    records = PayrollWageImportService.parse_csv(csv_text, column_map)
    assert records == [
        WageRecord(
            employee_id="A",
            wage=Decimal("1000000"),
            employment_insured=True,
            workers_comp_insured=True,
        )
    ]


def test_construction_business_rates():
    csv_text = "社員番号,賃金\nE1,10000000\n"
    records = PayrollWageImportService.parse_csv(csv_text)
    result = PayrollWageImportService.compute(records, business_type="construction")
    # construction 雇用 0.007 / 0.0105
    assert result.employment_employee_premium == Decimal("70000")
    assert result.employment_employer_premium == Decimal("105000")


def test_workers_comp_rate_override():
    csv_text = "社員番号,賃金\nE1,10000000\n"
    records = PayrollWageImportService.parse_csv(csv_text)
    result = PayrollWageImportService.compute(
        records, business_type="general", workers_comp_rate=Decimal("0.0088")
    )
    assert result.workers_comp_premium == Decimal("88000")


def test_empty_records_raises():
    with pytest.raises(ValueError, match="must not be empty"):
        PayrollWageImportService.compute([], business_type="general")


def test_invalid_business_type_raises():
    records = PayrollWageImportService.parse_csv("社員番号,賃金\nE1,1000000\n")
    with pytest.raises(ValueError, match="Unsupported business_type"):
        PayrollWageImportService.compute(records, business_type="unknown")


def test_negative_wage_raises():
    with pytest.raises(ValueError, match="must not be negative"):
        PayrollWageImportService.parse_csv("社員番号,賃金\nE1,-100\n")


def test_missing_wage_column_raises():
    with pytest.raises(ValueError, match="wage column not found"):
        PayrollWageImportService.parse_csv("社員番号,給料\nE1,1000000\n")


def test_unrecognized_flag_raises():
    with pytest.raises(ValueError, match="unrecognized insured flag"):
        PayrollWageImportService.parse_csv("社員番号,賃金,雇用保険対象\nE1,1000000,maybe\n")


def test_no_header_raises():
    with pytest.raises(ValueError, match="no header row"):
        PayrollWageImportService.parse_csv("")
