from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.schemas.schemas import JournalCreate, JournalLineCreate
from app.services.validation_engine import ValidationError, ValidationEngine


def _make_line(debit_credit: str, amount: str, tax: str = "0") -> JournalLineCreate:
    return JournalLineCreate(
        debit_credit=debit_credit,
        account_id=uuid4(),
        amount=Decimal(amount),
        tax_amount=Decimal(tax),
    )


def _make_journal(lines: list[JournalLineCreate]) -> JournalCreate:
    return JournalCreate(
        company_id=uuid4(),
        transaction_date=date(2026, 6, 26),
        lines=lines,
    )


class TestVal001DebitCreditBalance:
    def test_balanced_passes(self):
        journal = _make_journal([
            _make_line("debit", "10000"),
            _make_line("credit", "10000"),
        ])
        ValidationEngine.val_001_debit_credit_balance(journal)

    def test_unbalanced_raises(self):
        journal = _make_journal([
            _make_line("debit", "11000"),
            _make_line("credit", "10000"),
        ])
        with pytest.raises(ValidationError) as exc:
            ValidationEngine.val_001_debit_credit_balance(journal)
        assert exc.value.code == "VAL-001"

    def test_multi_line_balanced(self):
        journal = _make_journal([
            _make_line("debit", "5000"),
            _make_line("debit", "5000"),
            _make_line("credit", "10000"),
        ])
        ValidationEngine.val_001_debit_credit_balance(journal)


class TestVal002RequiredFields:
    def test_minimum_lines(self):
        journal = _make_journal([_make_line("debit", "100")])
        with pytest.raises(ValidationError) as exc:
            ValidationEngine.val_002_required_fields(journal)
        assert exc.value.code == "VAL-002"


class TestVal003AmountNonzero:
    def test_zero_amount_raises(self):
        journal = _make_journal([
            _make_line("debit", "0"),
            _make_line("credit", "0"),
        ])
        with pytest.raises(ValidationError) as exc:
            ValidationEngine.val_003_amount_nonzero(journal)
        assert exc.value.code == "VAL-005"


class TestVal004TaxConsistency:
    def test_negative_tax_raises(self):
        journal = _make_journal([
            _make_line("debit", "10000", "-100"),
            _make_line("credit", "10000"),
        ])
        with pytest.raises(ValidationError) as exc:
            ValidationEngine.val_004_tax_consistency(journal)
        assert exc.value.code == "VAL-004"


class TestVal005SoDCheck:
    def test_same_user_raises(self):
        uid = uuid4()
        with pytest.raises(ValidationError) as exc:
            ValidationEngine.val_005_sod_check(created_by=uid, approver_id=uid)
        assert exc.value.code == "SOD-001"

    def test_different_user_passes(self):
        ValidationEngine.val_005_sod_check(created_by=uuid4(), approver_id=uuid4())

    def test_no_approver_passes(self):
        ValidationEngine.val_005_sod_check(created_by=uuid4(), approver_id=None)


class TestFullValidation:
    def test_valid_journal_passes(self):
        journal = _make_journal([
            _make_line("debit", "10000"),
            _make_line("credit", "10000"),
        ])
        ValidationEngine.validate(journal, created_by=uuid4())

    def test_invalid_journal_fails(self):
        journal = _make_journal([
            _make_line("debit", "11000"),
            _make_line("credit", "10000"),
        ])
        with pytest.raises(ValidationError) as exc:
            ValidationEngine.validate(journal, created_by=uuid4())
        assert exc.value.code == "VAL-001"
