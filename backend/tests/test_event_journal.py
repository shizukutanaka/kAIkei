from decimal import Decimal

import pytest

from app.services.event_journal import (
    ROLE_ACCOUNTS_PAYABLE,
    ROLE_ACCOUNTS_RECEIVABLE,
    ROLE_CONSUMPTION_TAX_PAYABLE,
    ROLE_CONSUMPTION_TAX_RECEIVABLE,
    ROLE_SALES,
    EventJournalService,
)


def _line(draft, role):
    return next(line for line in draft.lines if line.account_role == role)


def test_sales_inclusive_splits_tax_and_balances():
    draft = EventJournalService.build_journal_draft(
        event_type="sales", amount=Decimal("11000"), tax_rate=Decimal("0.10"), is_tax_inclusive=True
    )
    assert _line(draft, ROLE_ACCOUNTS_RECEIVABLE).debit == Decimal("11000")
    assert _line(draft, ROLE_SALES).credit == Decimal("10000")
    assert _line(draft, ROLE_CONSUMPTION_TAX_PAYABLE).credit == Decimal("1000")
    assert draft.total_debit == draft.total_credit == Decimal("11000")


def test_sales_exclusive_adds_tax_on_top():
    draft = EventJournalService.build_journal_draft(
        event_type="sales", amount=Decimal("10000"), tax_rate=Decimal("0.10"), is_tax_inclusive=False
    )
    assert _line(draft, ROLE_ACCOUNTS_RECEIVABLE).debit == Decimal("11000")
    assert _line(draft, ROLE_SALES).credit == Decimal("10000")
    assert draft.total_debit == draft.total_credit


def test_purchase_expense_balances():
    draft = EventJournalService.build_journal_draft(
        event_type="purchase_expense", amount=Decimal("5500"), is_tax_inclusive=True
    )
    assert _line(draft, ROLE_ACCOUNTS_PAYABLE).credit == Decimal("5500")
    assert _line(draft, ROLE_CONSUMPTION_TAX_RECEIVABLE).debit == Decimal("500")
    assert draft.total_debit == draft.total_credit == Decimal("5500")


def test_payment_and_collection_have_no_tax_lines():
    payment = EventJournalService.build_journal_draft(event_type="payment", amount=Decimal("3000"))
    assert {line.account_role for line in payment.lines} == {ROLE_ACCOUNTS_PAYABLE, "bank_deposit"}
    assert payment.total_debit == payment.total_credit == Decimal("3000")

    collection = EventJournalService.build_journal_draft(event_type="collection", amount=Decimal("3000"))
    assert collection.total_debit == collection.total_credit == Decimal("3000")


def test_depreciation_balances_and_ignores_tax_rate():
    draft = EventJournalService.build_journal_draft(
        event_type="depreciation", amount=Decimal("12345"), tax_rate=Decimal("0.10")
    )
    assert draft.total_debit == draft.total_credit == Decimal("12345")
    assert all(
        line.account_role not in {ROLE_CONSUMPTION_TAX_PAYABLE, ROLE_CONSUMPTION_TAX_RECEIVABLE}
        for line in draft.lines
    )


def test_unsupported_event_raises():
    with pytest.raises(ValueError):
        EventJournalService.build_journal_draft(event_type="nope", amount=Decimal("100"))


def test_non_positive_amount_raises():
    with pytest.raises(ValueError):
        EventJournalService.build_journal_draft(event_type="sales", amount=Decimal("0"))


def test_supported_events_lists_all_builders():
    assert set(EventJournalService.supported_events()) == {
        "sales",
        "purchase_expense",
        "payment",
        "collection",
        "depreciation",
    }
