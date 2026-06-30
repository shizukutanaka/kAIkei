from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from app.models.models import BankStatementDetail, Invoice, PaymentRequest


@dataclass(frozen=True)
class ReconciliationCandidate:
    source_id: UUID
    source_type: str
    source_date: date
    amount: Decimal
    score: Decimal
    reason: str


class BankReconciliationService:
    @staticmethod
    def _score_amount(statement_amount: Decimal, source_amount: Decimal) -> Decimal:
        diff = abs(statement_amount - source_amount)
        if diff == 0:
            return Decimal("70")
        if diff <= Decimal("1"):
            return Decimal("55")
        if diff <= Decimal("10"):
            return Decimal("35")
        return Decimal("0")

    @staticmethod
    def _score_date(statement_date: date, source_date: date) -> Decimal:
        days = abs((statement_date - source_date).days)
        if days == 0:
            return Decimal("20")
        if days <= 3:
            return Decimal("10")
        if days <= 7:
            return Decimal("5")
        return Decimal("0")

    @classmethod
    def score_invoice_candidate(cls, statement: BankStatementDetail, invoice: Invoice) -> ReconciliationCandidate:
        statement_amount = statement.deposit_amount if statement.deposit_amount > 0 else statement.withdraw_amount
        base = cls._score_amount(statement_amount, invoice.total_amount)
        date_score = cls._score_date(statement.value_date, invoice.due_date)
        score = (base + date_score).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        reason = "入金額と請求書金額が一致" if base == Decimal("70") else "入金額が近い請求書候補"
        if date_score == Decimal("20"):
            reason += "、支払期限も一致"
        return ReconciliationCandidate(
            source_id=invoice.invoice_id,
            source_type="invoice",
            source_date=invoice.due_date,
            amount=invoice.total_amount,
            score=score,
            reason=reason,
        )

    @classmethod
    def score_payment_request_candidate(cls, statement: BankStatementDetail, payment_request: PaymentRequest) -> ReconciliationCandidate:
        statement_amount = statement.withdraw_amount if statement.withdraw_amount > 0 else statement.deposit_amount
        base = cls._score_amount(statement_amount, payment_request.payment_amount)
        date_score = cls._score_date(statement.value_date, payment_request.payment_date)
        score = (base + date_score).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        reason = "出金額と支払申請金額が一致" if base == Decimal("70") else "出金額が近い支払申請候補"
        if date_score == Decimal("20"):
            reason += "、支払日も一致"
        return ReconciliationCandidate(
            source_id=payment_request.payment_request_id,
            source_type="payment_request",
            source_date=payment_request.payment_date,
            amount=payment_request.payment_amount,
            score=score,
            reason=reason,
        )

    @classmethod
    def rank_candidates(
        cls,
        statement: BankStatementDetail,
        invoices: list[Invoice],
        payment_requests: list[PaymentRequest],
    ) -> list[ReconciliationCandidate]:
        candidates: list[ReconciliationCandidate] = []
        if statement.deposit_amount > 0:
            candidates.extend(cls.score_invoice_candidate(statement, inv) for inv in invoices)
        if statement.withdraw_amount > 0:
            candidates.extend(cls.score_payment_request_candidate(statement, pr) for pr in payment_requests)
        candidates = [c for c in candidates if c.score > 0]
        candidates.sort(key=lambda c: (c.score, c.source_date), reverse=True)
        return candidates
