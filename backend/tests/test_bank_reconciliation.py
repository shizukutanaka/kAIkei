from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.models.models import BankStatementDetail, Invoice, PaymentRequest
from app.services.bank_reconciliation import BankReconciliationService


def _statement(*, deposit: str = "0", withdraw: str = "0", value_date: date | None = None) -> BankStatementDetail:
    return BankStatementDetail(
        statement_detail_id=uuid4(),
        company_id=uuid4(),
        bank_account_id=uuid4(),
        value_date=value_date or date(2026, 6, 30),
        withdraw_amount=Decimal(withdraw),
        deposit_amount=Decimal(deposit),
        sender_name_kana="ﾃｽﾄ",
        description="",
    )


def _invoice(*, total: str, due_date: date) -> Invoice:
    return Invoice(
        invoice_id=uuid4(),
        company_id=uuid4(),
        partner_id=None,
        invoice_number="INV-001",
        invoice_date=due_date,
        due_date=due_date,
        subtotal=Decimal(total),
        tax_rate=Decimal("10.00"),
        tax_amount=Decimal("0"),
        total_amount=Decimal(total),
        status="issued",
        note=None,
    )


def _payment_request(*, amount: str, payment_date: date) -> PaymentRequest:
    return PaymentRequest(
        payment_request_id=uuid4(),
        company_id=uuid4(),
        partner_id=None,
        payment_date=payment_date,
        payment_amount=Decimal(amount),
        bank_account_id=None,
        dest_bank_code=None,
        dest_branch_code=None,
        dest_account_type=None,
        dest_account_no=None,
        dest_account_name_kana=None,
        status="approved",
        journal_header_id=None,
        zengin_export_batch_id=None,
        created_by=uuid4(),
    )


class TestInvoiceCandidate:
    def test_exact_amount_and_date_scores_highest(self):
        statement = _statement(deposit="11000", value_date=date(2026, 6, 30))
        invoice = _invoice(total="11000", due_date=date(2026, 6, 30))
        candidate = BankReconciliationService.score_invoice_candidate(statement, invoice)
        assert candidate.source_type == "invoice"
        assert candidate.score == Decimal("90.00")
        assert "一致" in candidate.reason

    def test_amount_mismatch_scores_lower(self):
        statement = _statement(deposit="11000", value_date=date(2026, 6, 30))
        invoice = _invoice(total="10995", due_date=date(2026, 7, 2))
        candidate = BankReconciliationService.score_invoice_candidate(statement, invoice)
        assert candidate.score == Decimal("45.00")


class TestPaymentRequestCandidate:
    def test_exact_amount_and_date_scores_highest(self):
        statement = _statement(withdraw="55000", value_date=date(2026, 6, 30))
        payment_request = _payment_request(amount="55000", payment_date=date(2026, 6, 30))
        candidate = BankReconciliationService.score_payment_request_candidate(statement, payment_request)
        assert candidate.source_type == "payment_request"
        assert candidate.score == Decimal("90.00")
        assert "一致" in candidate.reason


class TestRankCandidates:
    def test_deposit_matches_invoices_only(self):
        statement = _statement(deposit="12000")
        invoices = [
            _invoice(total="12000", due_date=date(2026, 6, 30)),
            _invoice(total="8000", due_date=date(2026, 6, 30)),
        ]
        payment_requests = [_payment_request(amount="12000", payment_date=date(2026, 6, 30))]
        candidates = BankReconciliationService.rank_candidates(statement, invoices, payment_requests)
        assert [c.source_type for c in candidates] == ["invoice", "invoice"]

    def test_withdraw_matches_payment_requests_only(self):
        statement = _statement(withdraw="12000")
        invoices = [_invoice(total="12000", due_date=date(2026, 6, 30))]
        payment_requests = [
            _payment_request(amount="12000", payment_date=date(2026, 6, 30)),
            _payment_request(amount="8000", payment_date=date(2026, 6, 30)),
        ]
        candidates = BankReconciliationService.rank_candidates(statement, invoices, payment_requests)
        assert [c.source_type for c in candidates] == ["payment_request", "payment_request"]
