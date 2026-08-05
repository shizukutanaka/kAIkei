from datetime import date
from decimal import Decimal

import pytest

from app.schemas.schemas import ReceivableMatchingResponse
from app.services.receivable_matching import (
    APPLY_AGGREGATE,
    APPLY_EXACT,
    APPLY_FEE_ADJUSTED,
    APPLY_PARTIAL,
    STATUS_ADVANCE,
    STATUS_PARTIAL,
    STATUS_SETTLED,
    STATUS_UNMATCHED,
    Deposit,
    OpenInvoice,
    ReceivableMatchingService,
)


def _invoice(invoice_id: str, amount: str, *, customer: str = "山田商事", due: str = "2025-08-31") -> OpenInvoice:
    return OpenInvoice(
        invoice_id=invoice_id,
        customer_name=customer,
        amount=Decimal(amount),
        due_date=date.fromisoformat(due),
    )


def _deposit(deposit_id: str, amount: str, *, remitter: str = "山田商事", txn: str = "2025-08-31") -> Deposit:
    return Deposit(
        deposit_id=deposit_id,
        transaction_date=date.fromisoformat(txn),
        amount=Decimal(amount),
        remitter_name=remitter,
    )


def test_exact_deposit_settles_invoice():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "110000")],
        invoices=[_invoice("I1", "110000")],
    )
    deposit = result.deposits[0]
    assert deposit.status == STATUS_SETTLED
    assert deposit.allocations[0].apply_type == APPLY_EXACT
    assert result.settled_invoice_ids == ["I1"]
    assert result.total_outstanding == Decimal("0")


def test_one_deposit_settles_multiple_invoices():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "330000")],
        invoices=[_invoice("I1", "110000"), _invoice("I2", "220000", due="2025-09-30")],
    )
    deposit = result.deposits[0]
    assert deposit.status == STATUS_SETTLED
    assert {a.apply_type for a in deposit.allocations} == {APPLY_AGGREGATE}
    assert sorted(a.invoice_id for a in deposit.allocations) == ["I1", "I2"]
    assert sorted(result.settled_invoice_ids) == ["I1", "I2"]


def test_bank_fee_deducted_deposit_settles_within_tolerance():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "109450")],
        invoices=[_invoice("I1", "110000")],
        fee_tolerance=Decimal("880"),
    )
    deposit = result.deposits[0]
    assert deposit.status == STATUS_SETTLED
    allocation = deposit.allocations[0]
    assert allocation.apply_type == APPLY_FEE_ADJUSTED
    assert allocation.applied_amount == Decimal("109450")
    assert allocation.fee_absorbed == Decimal("550")
    assert result.total_outstanding == Decimal("0")


def test_fee_beyond_tolerance_is_partial_not_settled():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "100000")],
        invoices=[_invoice("I1", "110000")],
        fee_tolerance=Decimal("880"),
    )
    deposit = result.deposits[0]
    assert deposit.status == STATUS_PARTIAL
    assert deposit.allocations[0].apply_type == APPLY_PARTIAL
    assert result.invoices[0].outstanding == Decimal("10000")
    assert result.settled_invoice_ids == []


def test_partial_deposits_accumulate_until_settled():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "40000"), _deposit("D2", "70000", txn="2025-09-05")],
        invoices=[_invoice("I1", "110000")],
    )
    assert result.deposits[0].status == STATUS_PARTIAL
    assert result.deposits[1].status == STATUS_SETTLED
    assert result.invoices[0].outstanding == Decimal("0")
    assert result.total_applied == Decimal("110000")


def test_partial_allocation_follows_due_date_order():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "150000")],
        invoices=[
            _invoice("I1", "100000", due="2025-09-30"),
            _invoice("I2", "100000", due="2025-07-31"),
        ],
    )
    allocations = result.deposits[0].allocations
    assert [a.invoice_id for a in allocations] == ["I2", "I1"]
    assert allocations[0].applied_amount == Decimal("100000")
    assert allocations[1].applied_amount == Decimal("50000")
    assert result.settled_invoice_ids == ["I2"]


def test_overpayment_is_kept_as_advance():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "150000")],
        invoices=[_invoice("I1", "110000")],
    )
    deposit = result.deposits[0]
    assert deposit.status == STATUS_ADVANCE
    assert deposit.applied_amount == Decimal("110000")
    assert deposit.advance_amount == Decimal("40000")
    assert result.total_advance == Decimal("40000")


def test_deposit_from_unknown_remitter_is_unmatched():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "110000", remitter="タナカ")],
        invoices=[_invoice("I1", "110000")],
    )
    assert result.deposits[0].status == STATUS_UNMATCHED
    assert result.unmatched_deposit_ids == ["D1"]
    # 相手先不明の入金を前受金に混ぜない(次回請求へ勝手に充当されるため)
    assert result.deposits[0].advance_amount == Decimal("0")
    assert result.total_advance == Decimal("0")
    assert result.total_unmatched == Decimal("110000")
    assert result.total_outstanding == Decimal("110000")


def test_other_customer_invoice_is_not_consumed():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "110000", remitter="山田商事")],
        invoices=[
            _invoice("I1", "110000", customer="鈴木工業"),
            _invoice("I2", "110000", customer="山田商事"),
        ],
    )
    assert result.deposits[0].allocations[0].invoice_id == "I2"
    assert result.settled_invoice_ids == ["I2"]


def test_corporate_suffix_difference_still_matches():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "110000", remitter="株式会社山田商事")],
        invoices=[_invoice("I1", "110000", customer="山田商事")],
    )
    assert result.deposits[0].status == STATUS_SETTLED


def test_exact_match_precedes_aggregate():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "100000")],
        invoices=[
            _invoice("I1", "100000"),
            _invoice("I2", "40000"),
            _invoice("I3", "60000"),
        ],
    )
    assert result.deposits[0].allocations[0].invoice_id == "I1"
    assert result.deposits[0].allocations[0].apply_type == APPLY_EXACT


def test_invoice_is_not_over_applied_across_deposits():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "110000"), _deposit("D2", "110000", txn="2025-09-01")],
        invoices=[_invoice("I1", "110000")],
    )
    assert result.deposits[1].status == STATUS_UNMATCHED
    assert result.invoices[0].applied_amount == Decimal("110000")
    assert result.total_applied == Decimal("110000")


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError, match="deposit_id"):
        ReceivableMatchingService.match(
            deposits=[_deposit("D1", "100"), _deposit("D1", "200")],
            invoices=[_invoice("I1", "300")],
        )
    with pytest.raises(ValueError, match="invoice_id"):
        ReceivableMatchingService.match(
            deposits=[_deposit("D1", "100")],
            invoices=[_invoice("I1", "100"), _invoice("I1", "200")],
        )


def test_invalid_values_rejected():
    with pytest.raises(ValueError, match="fee_tolerance"):
        ReceivableMatchingService.match(
            deposits=[_deposit("D1", "100")],
            invoices=[_invoice("I1", "100")],
            fee_tolerance=Decimal("-1"),
        )
    with pytest.raises(ValueError, match="name_threshold"):
        ReceivableMatchingService.match(
            deposits=[_deposit("D1", "100")],
            invoices=[_invoice("I1", "100")],
            name_threshold=1.5,
        )
    with pytest.raises(ValueError, match="deposit amount"):
        ReceivableMatchingService.match(
            deposits=[_deposit("D1", "0")],
            invoices=[_invoice("I1", "100")],
        )
    with pytest.raises(ValueError, match="invoice amount"):
        ReceivableMatchingService.match(
            deposits=[_deposit("D1", "100")],
            invoices=[_invoice("I1", "-100")],
        )


def test_empty_input_returns_zero_totals():
    result = ReceivableMatchingService.match(deposits=[], invoices=[])
    assert result.total_applied == Decimal("0")
    assert result.total_advance == Decimal("0")
    assert result.total_unmatched == Decimal("0")
    assert result.total_outstanding == Decimal("0")
    assert result.unmatched_deposit_ids == []


def test_response_schema_serializes_dataclass():
    result = ReceivableMatchingService.match(
        deposits=[_deposit("D1", "150000")],
        invoices=[_invoice("I1", "110000")],
    )
    payload = ReceivableMatchingResponse.model_validate(result)
    assert payload.deposits[0].advance_amount == Decimal("40000")
    assert payload.invoices[0].settled is True
