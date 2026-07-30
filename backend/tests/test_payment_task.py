"""納付事務タスク生成のテスト。"""

from datetime import date
from decimal import Decimal

import pytest

from app.schemas.schemas import PaymentTaskResponse
from app.services.payment_task import (
    PAYEE_MUNICIPALITY,
    PAYEE_SOCIAL_INSURANCE,
    PAYEE_TAX_OFFICE,
    TASK_RESIDENCE_TAX,
    TASK_SOCIAL_INSURANCE,
    TASK_WITHHOLDING_TAX,
    PaymentTaskInput,
    PaymentTaskService,
)


def _generate(**kwargs):
    return PaymentTaskService.generate(PaymentTaskInput(**kwargs))


def test_generates_three_payment_tasks_with_payees():
    result = _generate(
        payroll_year=2025,
        payroll_month=7,
        income_tax=Decimal("90000"),
        residence_tax=Decimal("60000"),
        social_insurance_total=Decimal("925500"),
    )
    assert [task.task_type for task in result.tasks] == [
        TASK_WITHHOLDING_TAX,
        TASK_RESIDENCE_TAX,
        TASK_SOCIAL_INSURANCE,
    ]
    assert [task.payee for task in result.tasks] == [
        PAYEE_TAX_OFFICE,
        PAYEE_MUNICIPALITY,
        PAYEE_SOCIAL_INSURANCE,
    ]
    assert result.total_amount == Decimal("1075500")


def test_due_date_shifts_to_next_business_day_when_statutory_date_is_sunday():
    # 2025-08-10 は日曜、2025-08-31 も日曜。
    result = _generate(
        payroll_year=2025,
        payroll_month=7,
        income_tax=Decimal("90000"),
        social_insurance_total=Decimal("925500"),
    )
    withholding, social = result.tasks
    assert withholding.statutory_due_date == date(2025, 8, 10)
    assert withholding.due_date == date(2025, 8, 11)
    assert withholding.shifted is True
    assert social.statutory_due_date == date(2025, 8, 31)
    assert social.due_date == date(2025, 9, 1)
    assert result.earliest_due_date == date(2025, 8, 11)


def test_due_date_not_shifted_when_statutory_date_is_business_day():
    # 2025-10-10 は金曜。
    result = _generate(
        payroll_year=2025,
        payroll_month=9,
        income_tax=Decimal("50000"),
    )
    task = result.tasks[0]
    assert task.statutory_due_date == date(2025, 10, 10)
    assert task.due_date == date(2025, 10, 10)
    assert task.shifted is False


def test_year_end_closed_period_shifts_into_january():
    # 2025年11月分の社会保険料は法定12/31だが12/29〜1/3は休日扱い、1/4は日曜。
    result = _generate(
        payroll_year=2025,
        payroll_month=11,
        social_insurance_total=Decimal("500000"),
    )
    task = result.tasks[0]
    assert task.statutory_due_date == date(2025, 12, 31)
    assert task.due_date == date(2026, 1, 5)
    assert task.shifted is True


def test_supplied_holiday_shifts_due_date():
    # 2025-11-10(月)を休日として渡すと翌日へ動く。
    result = _generate(
        payroll_year=2025,
        payroll_month=10,
        income_tax=Decimal("10000"),
        holidays=[date(2025, 11, 10)],
    )
    task = result.tasks[0]
    assert task.statutory_due_date == date(2025, 11, 10)
    assert task.due_date == date(2025, 11, 11)


def test_withholding_special_exception_first_half_due_july_10():
    result = _generate(
        payroll_year=2025,
        payroll_month=3,
        income_tax=Decimal("120000"),
        withholding_special_exception=True,
    )
    task = result.tasks[0]
    assert task.statutory_due_date == date(2025, 7, 10)
    assert task.due_date == date(2025, 7, 10)
    assert task.legal_basis == "所得税法216条"
    assert "納期の特例" in task.title


def test_withholding_special_exception_second_half_due_next_january_20():
    result = _generate(
        payroll_year=2025,
        payroll_month=12,
        income_tax=Decimal("120000"),
        withholding_special_exception=True,
    )
    task = result.tasks[0]
    assert task.statutory_due_date == date(2026, 1, 20)
    assert task.due_date == date(2026, 1, 20)


def test_december_payroll_crosses_year_without_exception():
    result = _generate(
        payroll_year=2025,
        payroll_month=12,
        income_tax=Decimal("90000"),
        social_insurance_total=Decimal("500000"),
    )
    withholding, social = result.tasks
    # 2026-01-10 は土曜、1/11は日曜、1/12は月曜。
    assert withholding.statutory_due_date == date(2026, 1, 10)
    assert withholding.due_date == date(2026, 1, 12)
    assert social.statutory_due_date == date(2026, 1, 31)
    assert social.due_date == date(2026, 2, 2)


def test_february_month_end_social_insurance():
    result = _generate(
        payroll_year=2024,
        payroll_month=1,
        social_insurance_total=Decimal("300000"),
    )
    assert result.tasks[0].statutory_due_date == date(2024, 2, 29)


def test_zero_amount_tasks_are_omitted():
    result = _generate(
        payroll_year=2025,
        payroll_month=7,
        residence_tax=Decimal("60000"),
    )
    assert [task.task_type for task in result.tasks] == [TASK_RESIDENCE_TAX]
    assert result.total_amount == Decimal("60000")


def test_all_zero_amounts_rejected():
    with pytest.raises(ValueError, match="at least one payment amount"):
        _generate(payroll_year=2025, payroll_month=7)


def test_negative_amount_rejected():
    with pytest.raises(ValueError, match="must not be negative"):
        _generate(
            payroll_year=2025,
            payroll_month=7,
            income_tax=Decimal("-1"),
        )


def test_invalid_month_rejected():
    with pytest.raises(ValueError, match="payroll_month"):
        _generate(
            payroll_year=2025,
            payroll_month=13,
            income_tax=Decimal("1000"),
        )


def test_response_schema_serializes_dataclass():
    result = _generate(
        payroll_year=2025,
        payroll_month=7,
        income_tax=Decimal("90000"),
        social_insurance_total=Decimal("925500"),
    )
    response = PaymentTaskResponse.model_validate(result)
    assert response.tasks[0].due_date == date(2025, 8, 11)
    assert response.earliest_due_date == date(2025, 8, 11)
