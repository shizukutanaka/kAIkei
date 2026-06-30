from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.audit_inspection import AuditInspectionService


def _header(company_id, journal_header_id, transaction_date, created_at, is_deleted=False, is_voided=False):
    return SimpleNamespace(
        company_id=company_id,
        journal_header_id=journal_header_id,
        transaction_date=transaction_date,
        created_at=created_at,
        is_deleted=is_deleted,
        is_voided=is_voided,
    )


def _line(journal_header_id, account_id, debit_credit, amount, is_deleted=False):
    return SimpleNamespace(
        journal_header_id=journal_header_id,
        account_id=account_id,
        debit_credit=debit_credit,
        amount=Decimal(str(amount)),
        is_deleted=is_deleted,
    )


class TestAuditInspectionService:
    def test_duplicate_peer_triggers_duplicate_detection(self):
        company_id = uuid4()
        header_id = uuid4()
        peer_header_id = uuid4()
        account_a = uuid4()
        account_b = uuid4()
        created_at = datetime(2026, 6, 30, 10, 0, 0)

        target_header = _header(company_id, header_id, datetime(2026, 6, 1).date(), created_at)
        target_lines = [
            _line(header_id, account_a, "debit", "100"),
            _line(header_id, account_b, "credit", "100"),
        ]
        peer_header = _header(company_id, peer_header_id, datetime(2026, 6, 1).date(), created_at)
        peer_lines = [
            _line(peer_header_id, account_b, "credit", "100"),
            _line(peer_header_id, account_a, "debit", "100"),
        ]

        detections = AuditInspectionService.inspect(
            target_header=target_header,
            target_lines=target_lines,
            peer_headers_with_lines=[(peer_header, peer_lines)],
        )

        assert [(d.risk_level, d.category) for d in detections] == [("critical", "duplicate")]

    def test_after_hours_triggers_info(self):
        company_id = uuid4()
        header_id = uuid4()
        target_header = _header(
            company_id,
            header_id,
            datetime(2026, 6, 1).date(),
            datetime(2026, 6, 1, 2, 30, 0),
        )

        detections = AuditInspectionService.inspect(
            target_header=target_header,
            target_lines=[],
            peer_headers_with_lines=[],
        )

        assert [(d.risk_level, d.category) for d in detections] == [("info", "after_hours")]

    def test_circular_triggers_warning(self):
        company_id = uuid4()
        header_id = uuid4()
        account_id = uuid4()
        target_header = _header(company_id, header_id, datetime(2026, 6, 1).date(), datetime(2026, 6, 1, 10, 0, 0))
        target_lines = [
            _line(header_id, account_id, "debit", "100"),
            _line(header_id, account_id, "credit", "100"),
        ]

        detections = AuditInspectionService.inspect(
            target_header=target_header,
            target_lines=target_lines,
            peer_headers_with_lines=[],
        )

        assert [(d.risk_level, d.category) for d in detections] == [("warning", "circular")]

    def test_large_amount_triggers_warning(self):
        company_id = uuid4()
        header_id = uuid4()
        account_a = uuid4()
        account_b = uuid4()
        target_header = _header(company_id, header_id, datetime(2026, 6, 1).date(), datetime(2026, 6, 1, 10, 0, 0))
        target_lines = [
            _line(header_id, account_a, "debit", "12000000"),
            _line(header_id, account_b, "credit", "12000000"),
        ]

        detections = AuditInspectionService.inspect(
            target_header=target_header,
            target_lines=target_lines,
            peer_headers_with_lines=[],
        )

        assert [(d.risk_level, d.category) for d in detections] == [("warning", "large_amount")]

    def test_clean_journal_returns_empty_list(self):
        company_id = uuid4()
        header_id = uuid4()
        account_a = uuid4()
        account_b = uuid4()
        target_header = _header(company_id, header_id, datetime(2026, 6, 1).date(), datetime(2026, 6, 1, 10, 0, 0))
        target_lines = [
            _line(header_id, account_a, "debit", "100"),
            _line(header_id, account_b, "credit", "100"),
        ]

        detections = AuditInspectionService.inspect(
            target_header=target_header,
            target_lines=target_lines,
            peer_headers_with_lines=[],
        )

        assert detections == []
