from datetime import date
from decimal import Decimal

import pytest

from app.models.models import Account, JournalHeader, JournalLine
from app.services import audit_detection

pytestmark = pytest.mark.db


async def _seed_high_amount_journal(db_session, company_id, user_id):
    account = Account(
        company_id=company_id, account_code="5210", account_name="交際費",
        account_type="expense", debit_credit="debit",
    )
    db_session.add(account)
    await db_session.flush()
    header = JournalHeader(
        company_id=company_id, journal_number="J-HIGH", transaction_date=date(2026, 4, 15), created_by=user_id,
    )
    db_session.add(header)
    await db_session.flush()
    db_session.add(JournalLine(
        journal_header_id=header.journal_header_id, line_number=1, debit_credit="debit",
        account_id=account.account_id, amount=Decimal("2000000"), description="高額接待",
    ))
    await db_session.flush()


async def test_scan_creates_detections_idempotently(db_session, seed_company):
    tid, cid, uid = seed_company["tenant_id"], seed_company["company_id"], seed_company["user_id"]
    await _seed_high_amount_journal(db_session, cid, uid)

    result = await audit_detection.scan_company(db_session, tid, cid)
    assert result["scanned"] == 1
    assert result["detections_created"] >= 1

    detections = await audit_detection.list_detections(db_session, cid)
    cats = {d.category for d in detections}
    assert "high_amount" in cats  # 2,000,000 >= threshold

    # re-scan does not duplicate
    again = await audit_detection.scan_company(db_session, tid, cid)
    assert again["detections_created"] == 0

    # status update
    target = detections[0]
    updated = await audit_detection.update_status(db_session, cid, target.audit_detection_log_id, "confirmed", uid)
    assert updated.status == "confirmed"
