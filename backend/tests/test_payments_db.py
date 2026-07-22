from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.models import PaymentRequest
from app.services.payment_workflow import next_payment_status

pytestmark = pytest.mark.db


async def _make_payment(db, company_id, created_by, status="draft", amount="10000"):
    req = PaymentRequest(
        company_id=company_id,
        payment_date=date(2026, 6, 30),
        payment_amount=Decimal(amount),
        dest_account_name_kana="ﾃｽﾄ",
        status=status,
        created_by=created_by,
    )
    db.add(req)
    await db.flush()
    return req


async def test_list_and_status_filter(db_session, seed_company):
    cid, uid = seed_company["company_id"], seed_company["user_id"]
    await _make_payment(db_session, cid, uid, status="draft")
    await _make_payment(db_session, cid, uid, status="approved")

    all_rows = (await db_session.execute(
        select(PaymentRequest).where(PaymentRequest.company_id == cid)
    )).scalars().all()
    assert len(all_rows) == 2

    approved = (await db_session.execute(
        select(PaymentRequest).where(
            PaymentRequest.company_id == cid, PaymentRequest.status == "approved"
        )
    )).scalars().all()
    assert len(approved) == 1
    assert approved[0].status == "approved"


async def test_transition_lifecycle_persists(db_session, seed_company):
    cid, uid = seed_company["company_id"], seed_company["user_id"]
    req = await _make_payment(db_session, cid, uid, status="draft")

    # draft -> approved -> executed
    req.status = next_payment_status(req.status, "approve")
    await db_session.flush()
    req.status = next_payment_status(req.status, "execute")
    await db_session.flush()

    fetched = (await db_session.execute(
        select(PaymentRequest).where(PaymentRequest.payment_request_id == req.payment_request_id)
    )).scalar_one()
    assert fetched.status == "executed"


async def test_zengin_export_query_finds_only_approved_or_executed(db_session, seed_company):
    """支払申請が承認/実行済みになって初めて全銀エクスポートの対象になることを確認。"""
    cid, uid = seed_company["company_id"], seed_company["user_id"]
    await _make_payment(db_session, cid, uid, status="draft")
    await _make_payment(db_session, cid, uid, status="approved")
    await _make_payment(db_session, cid, uid, status="executed")
    await _make_payment(db_session, cid, uid, status="cancelled")

    exportable = (await db_session.execute(
        select(PaymentRequest).where(
            PaymentRequest.company_id == cid,
            PaymentRequest.status.in_(("approved", "executed")),
        )
    )).scalars().all()
    assert {r.status for r in exportable} == {"approved", "executed"}
    assert len(exportable) == 2
