from decimal import Decimal

import pytest

from app.services.monthly_payslip import MonthlyPayslipService


def test_integrated_monthly_payslip():
    result = MonthlyPayslipService.compute(
        base_salary=Decimal("300000"),
        standard_monthly_remuneration=Decimal("300000"),
        overtime_pay=Decimal("20000"),
        other_taxable_allowances=Decimal("10000"),
        non_taxable_commute_allowance=Decimal("10000"),
        income_tax=Decimal("6000"),
        residence_tax=Decimal("12000"),
    )
    assert result.taxable_earnings == Decimal("330000")
    assert result.total_earnings == Decimal("340000")
    assert result.social_insurance_employee == Decimal("42420")
    assert result.employment_insurance_employee == Decimal("2040")
    assert result.total_deductions == Decimal("62460")
    assert result.net_pay == Decimal("277540")


def test_employment_insurance_exempt():
    result = MonthlyPayslipService.compute(
        base_salary=Decimal("300000"),
        standard_monthly_remuneration=Decimal("300000"),
        employment_insurance_exempt=True,
    )
    assert result.employment_insurance_employee == Decimal("0")


def test_care_insurance_applied():
    result = MonthlyPayslipService.compute(
        base_salary=Decimal("300000"),
        standard_monthly_remuneration=Decimal("300000"),
        care_applicable=True,
    )
    # 介護 300000*0.016=4800 -> employee 2400 added to health+pension employee
    assert result.social_insurance.care.employee == Decimal("2400")
    assert result.social_insurance_employee == Decimal("44820")


def test_negative_input_raises():
    with pytest.raises(ValueError):
        MonthlyPayslipService.compute(
            base_salary=Decimal("-1"),
            standard_monthly_remuneration=Decimal("300000"),
        )
