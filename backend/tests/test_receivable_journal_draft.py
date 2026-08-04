from datetime import date
from decimal import Decimal

import pytest

from app.services.receivable_journal_draft import (
    DRAFT_RECEIVABLE_SETTLEMENT,
    DRAFT_SUSPENSE_RECEIPT,
    ROLE_ACCOUNTS_RECEIVABLE,
    ROLE_ADVANCE_RECEIVED,
    ROLE_BANK_DEPOSIT,
    ROLE_SUSPENSE_RECEIPT,
    ROLE_TRANSFER_FEE_EXPENSE,
    ReceivableJournalDraftService,
)
from app.services.receivable_matching import (
    Deposit,
    OpenInvoice,
    ReceivableMatchingService,
)

TXN = date(2025, 8, 31)


def _generate(deposits, invoices, **kwargs):
    result = ReceivableMatchingService.match(deposits=deposits, invoices=invoices, **kwargs)
    return ReceivableJournalDraftService.generate(
        result,
        transaction_dates={d.deposit_id: d.transaction_date for d in deposits},
        partner_names={i.invoice_id: i.customer_name for i in invoices},
    )


def _deposit(deposit_id: str, amount: str, remitter: str = "山田商事") -> Deposit:
    return Deposit(
        deposit_id=deposit_id,
        transaction_date=TXN,
        amount=Decimal(amount),
        remitter_name=remitter,
    )


def _invoice(invoice_id: str, amount: str, customer: str = "山田商事") -> OpenInvoice:
    return OpenInvoice(
        invoice_id=invoice_id,
        customer_name=customer,
        amount=Decimal(amount),
        due_date=TXN,
    )


def _amount(draft, role: str, *, debit: bool) -> Decimal:
    return sum(
        ((line.debit if debit else line.credit) for line in draft.lines if line.account_role == role),
        Decimal("0"),
    )


def test_exact_settlement_draft():
    result = _generate([_deposit("D1", "110000")], [_invoice("I1", "110000")])
    draft = result.drafts[0]
    assert draft.draft_type == DRAFT_RECEIVABLE_SETTLEMENT
    assert draft.transaction_date == TXN
    assert _amount(draft, ROLE_BANK_DEPOSIT, debit=True) == Decimal("110000")
    assert _amount(draft, ROLE_ACCOUNTS_RECEIVABLE, debit=False) == Decimal("110000")
    assert draft.total_debit == draft.total_credit == Decimal("110000")
    assert result.balanced is True


def test_fee_deducted_deposit_clears_full_receivable():
    result = _generate(
        [_deposit("D1", "109450")],
        [_invoice("I1", "110000")],
        fee_tolerance=Decimal("880"),
    )
    draft = result.drafts[0]
    # 入金額ではなく請求全額を落とし、差額は支払手数料にする
    assert _amount(draft, ROLE_ACCOUNTS_RECEIVABLE, debit=False) == Decimal("110000")
    assert _amount(draft, ROLE_TRANSFER_FEE_EXPENSE, debit=True) == Decimal("550")
    assert _amount(draft, ROLE_BANK_DEPOSIT, debit=True) == Decimal("109450")
    assert draft.total_debit == draft.total_credit == Decimal("110000")
    assert result.total_fee_expense == Decimal("550")


def test_overpayment_goes_to_advance_received():
    result = _generate([_deposit("D1", "150000")], [_invoice("I1", "110000")])
    draft = result.drafts[0]
    assert _amount(draft, ROLE_ACCOUNTS_RECEIVABLE, debit=False) == Decimal("110000")
    assert _amount(draft, ROLE_ADVANCE_RECEIVED, debit=False) == Decimal("40000")
    assert result.total_advance_received == Decimal("40000")


def test_partial_deposit_clears_only_applied_amount():
    result = _generate([_deposit("D1", "40000")], [_invoice("I1", "110000")])
    draft = result.drafts[0]
    assert _amount(draft, ROLE_ACCOUNTS_RECEIVABLE, debit=False) == Decimal("40000")
    assert _amount(draft, ROLE_ADVANCE_RECEIVED, debit=False) == Decimal("0")


def test_aggregate_deposit_creates_line_per_invoice():
    result = _generate(
        [_deposit("D1", "330000")],
        [_invoice("I1", "110000"), _invoice("I2", "220000")],
    )
    lines = [
        line for line in result.drafts[0].lines if line.account_role == ROLE_ACCOUNTS_RECEIVABLE
    ]
    assert sorted((line.invoice_id, line.credit) for line in lines) == [
        ("I1", Decimal("110000")),
        ("I2", Decimal("220000")),
    ]
    assert {line.partner_name for line in lines} == {"山田商事"}


def test_unmatched_deposit_is_booked_as_suspense():
    result = _generate([_deposit("D1", "50000", remitter="不明")], [_invoice("I1", "110000")])
    draft = result.drafts[0]
    assert draft.draft_type == DRAFT_SUSPENSE_RECEIPT
    assert _amount(draft, ROLE_BANK_DEPOSIT, debit=True) == Decimal("50000")
    assert _amount(draft, ROLE_SUSPENSE_RECEIPT, debit=False) == Decimal("50000")
    assert result.total_suspense == Decimal("50000")
    assert result.total_receivable_cleared == Decimal("0")


def test_every_draft_is_balanced_in_mixed_scenario():
    deposits = [
        _deposit("D1", "330000"),
        _deposit("D2", "109450", remitter="鈴木工業"),
        _deposit("D3", "200000", remitter="田中製作所"),
        _deposit("D4", "50000", remitter="不明"),
    ]
    invoices = [
        _invoice("I1", "110000"),
        _invoice("I2", "220000"),
        _invoice("I3", "110000", customer="鈴木工業"),
        _invoice("I4", "150000", customer="田中製作所"),
    ]
    result = _generate(deposits, invoices, fee_tolerance=Decimal("880"))
    assert len(result.drafts) == 4
    assert all(d.total_debit == d.total_credit for d in result.drafts)
    assert result.total_receivable_cleared == Decimal("590000")
    assert result.total_fee_expense == Decimal("550")
    assert result.total_advance_received == Decimal("50000")
    assert result.total_suspense == Decimal("50000")


def test_missing_transaction_date_rejected():
    deposits = [_deposit("D1", "110000")]
    invoices = [_invoice("I1", "110000")]
    matched = ReceivableMatchingService.match(deposits=deposits, invoices=invoices)
    with pytest.raises(ValueError, match="transaction_date"):
        ReceivableJournalDraftService.generate(matched, transaction_dates={})


def test_no_deposits_produces_no_drafts():
    result = _generate([], [])
    assert result.drafts == []
    assert result.balanced is True
    assert result.total_receivable_cleared == Decimal("0")
