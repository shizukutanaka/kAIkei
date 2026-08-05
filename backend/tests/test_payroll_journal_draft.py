from datetime import date
from decimal import Decimal

import pytest

from app.schemas.schemas import PayrollJournalDraftResponse
from app.services.payroll_journal_draft import (
    DRAFT_PAYROLL,
    DRAFT_RESIDENCE_TAX_PAYMENT,
    DRAFT_SOCIAL_INSURANCE_PAYMENT,
    DRAFT_WITHHOLDING_TAX_PAYMENT,
    ROLE_BANK_DEPOSIT,
    ROLE_INCOME_TAX_WITHHOLDING,
    ROLE_LEGAL_WELFARE_EXPENSE,
    ROLE_OTHER_DEDUCTION_PAYABLE,
    ROLE_SALARY_EXPENSE,
    ROLE_SOCIAL_INSURANCE_PAYABLE,
    ROLE_SOCIAL_INSURANCE_WITHHOLDING,
    PayrollJournalDraftService,
    PayrollJournalInput,
)


def _input(**kwargs) -> PayrollJournalInput:
    base = {
        "payroll_year": 2025,
        "payroll_month": 7,
        "total_gross": Decimal("3000000"),
        "employee_social_insurance": Decimal("420000"),
        "employee_employment_insurance": Decimal("18000"),
        "income_tax": Decimal("90000"),
        "residence_tax": Decimal("60000"),
        "employer_social_insurance": Decimal("450000"),
        "employer_employment_insurance": Decimal("28500"),
        "employer_workers_compensation": Decimal("9000"),
    }
    base.update(kwargs)
    return PayrollJournalInput(**base)


def _draft(result, draft_type):
    return next(draft for draft in result.drafts if draft.draft_type == draft_type)


def _amount(draft, role, side):
    line = next(line for line in draft.lines if line.account_role == role)
    return line.debit if side == "debit" else line.credit


def test_net_pay_is_derived_from_deductions():
    result = PayrollJournalDraftService.generate(_input())

    assert result.employee_deduction_total == Decimal("588000")
    assert result.net_pay == Decimal("2412000")
    assert result.employer_burden_total == Decimal("487500")


def test_payroll_draft_is_balanced_with_employer_burden():
    draft = _draft(PayrollJournalDraftService.generate(_input()), DRAFT_PAYROLL)

    assert _amount(draft, ROLE_SALARY_EXPENSE, "debit") == Decimal("3000000")
    assert _amount(draft, ROLE_LEGAL_WELFARE_EXPENSE, "debit") == Decimal("487500")
    assert _amount(draft, ROLE_SOCIAL_INSURANCE_WITHHOLDING, "credit") == Decimal("438000")
    assert _amount(draft, ROLE_SOCIAL_INSURANCE_PAYABLE, "credit") == Decimal("487500")
    assert _amount(draft, ROLE_BANK_DEPOSIT, "credit") == Decimal("2412000")
    assert draft.total_debit == draft.total_credit == Decimal("3487500")
    assert draft.transaction_date == date(2025, 7, 25)
    assert draft.due_date is None


def test_withholding_and_residence_tax_due_on_10th_of_next_month():
    result = PayrollJournalDraftService.generate(_input())

    tax = _draft(result, DRAFT_WITHHOLDING_TAX_PAYMENT)
    residence = _draft(result, DRAFT_RESIDENCE_TAX_PAYMENT)

    assert tax.due_date == date(2025, 8, 10)
    assert _amount(tax, ROLE_INCOME_TAX_WITHHOLDING, "debit") == Decimal("90000")
    assert residence.due_date == date(2025, 8, 10)
    assert residence.total_debit == Decimal("60000")


def test_social_insurance_payment_due_on_last_day_of_next_month():
    social = _draft(
        PayrollJournalDraftService.generate(_input()), DRAFT_SOCIAL_INSURANCE_PAYMENT
    )

    assert social.due_date == date(2025, 8, 31)
    assert _amount(social, ROLE_SOCIAL_INSURANCE_WITHHOLDING, "debit") == Decimal("438000")
    assert _amount(social, ROLE_SOCIAL_INSURANCE_PAYABLE, "debit") == Decimal("487500")
    assert _amount(social, ROLE_BANK_DEPOSIT, "credit") == Decimal("925500")


def test_january_payroll_deadline_uses_last_day_of_february():
    result = PayrollJournalDraftService.generate(_input(payroll_year=2025, payroll_month=1))

    assert _draft(result, DRAFT_SOCIAL_INSURANCE_PAYMENT).due_date == date(2025, 2, 28)
    assert _draft(result, DRAFT_WITHHOLDING_TAX_PAYMENT).due_date == date(2025, 2, 10)


def test_december_payroll_deadline_crosses_year():
    result = PayrollJournalDraftService.generate(_input(payroll_year=2025, payroll_month=12))

    assert _draft(result, DRAFT_WITHHOLDING_TAX_PAYMENT).due_date == date(2026, 1, 10)
    assert _draft(result, DRAFT_SOCIAL_INSURANCE_PAYMENT).due_date == date(2026, 1, 31)


def test_zero_amount_lines_are_omitted():
    draft = _draft(
        PayrollJournalDraftService.generate(
            _input(
                residence_tax=Decimal("0"),
                other_deductions=Decimal("0"),
                employer_workers_compensation=Decimal("0"),
            ),
        ),
        DRAFT_PAYROLL,
    )
    roles = [line.account_role for line in draft.lines]

    assert ROLE_OTHER_DEDUCTION_PAYABLE not in roles
    assert draft.total_debit == draft.total_credit


def test_no_deduction_payroll_has_only_payroll_draft():
    result = PayrollJournalDraftService.generate(
        PayrollJournalInput(
            payroll_year=2025,
            payroll_month=7,
            total_gross=Decimal("500000"),
        ),
    )

    assert [draft.draft_type for draft in result.drafts] == [DRAFT_PAYROLL]
    assert result.net_pay == Decimal("500000")
    assert result.balanced is True


def test_other_deductions_are_carried_to_payable():
    draft = _draft(
        PayrollJournalDraftService.generate(_input(other_deductions=Decimal("12000"))),
        DRAFT_PAYROLL,
    )

    assert _amount(draft, ROLE_OTHER_DEDUCTION_PAYABLE, "credit") == Decimal("12000")
    assert _amount(draft, ROLE_BANK_DEPOSIT, "credit") == Decimal("2400000")


def test_custom_payment_day_sets_transaction_date():
    draft = _draft(
        PayrollJournalDraftService.generate(_input(payment_day=15)), DRAFT_PAYROLL
    )

    assert draft.transaction_date == date(2025, 7, 15)


def test_response_schema_validates_service_result():
    result = PayrollJournalDraftService.generate(_input())

    response = PayrollJournalDraftResponse.model_validate(result)

    assert response.net_pay == Decimal("2412000")
    assert response.drafts[0].lines[0].account_role == ROLE_SALARY_EXPENSE


def test_deductions_exceeding_gross_rejected():
    with pytest.raises(ValueError, match="deductions must not exceed total_gross"):
        PayrollJournalDraftService.generate(
            _input(total_gross=Decimal("100000"), income_tax=Decimal("200000")),
        )


def test_negative_amount_rejected():
    with pytest.raises(ValueError, match="must not be negative"):
        PayrollJournalDraftService.generate(_input(income_tax=Decimal("-1")))


def test_zero_gross_rejected():
    with pytest.raises(ValueError, match="total_gross must be positive"):
        PayrollJournalDraftService.generate(_input(total_gross=Decimal("0")))


def test_payment_day_outside_month_rejected():
    with pytest.raises(ValueError, match="payment_day"):
        PayrollJournalDraftService.generate(
            _input(payroll_year=2025, payroll_month=2, payment_day=30),
        )


def test_invalid_month_rejected():
    with pytest.raises(ValueError, match="payroll_month"):
        PayrollJournalDraftService.generate(_input(payroll_month=0))
