from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.models import Invoice, Partner
from app.services import ar_aging

pytestmark = pytest.mark.db

AS_OF = date(2026, 6, 30)


async def _invoice(db, company_id, partner_id, number, due, amount, status="issued"):
    inv = Invoice(
        company_id=company_id,
        partner_id=partner_id,
        invoice_number=number,
        invoice_date=date(2026, 1, 1),
        due_date=due,
        subtotal=Decimal(amount),
        tax_rate=Decimal("0.10"),
        tax_amount=Decimal("0"),
        total_amount=Decimal(amount),
        status=status,
    )
    db.add(inv)
    await db.flush()
    return inv


async def test_aging_aggregates_real_invoices_by_partner_and_bucket(db_session, seed_company):
    cid = seed_company["company_id"]
    p1 = Partner(company_id=cid, partner_code="P1", partner_name="大口物産", partner_type="customer")
    p2 = Partner(company_id=cid, partner_code="P2", partner_name="小口商事", partner_type="customer")
    db_session.add_all([p1, p2])
    await db_session.flush()

    await _invoice(db_session, cid, p1.partner_id, "INV-1", date(2026, 7, 10), "1000")  # 未到来
    await _invoice(db_session, cid, p1.partner_id, "INV-2", date(2026, 6, 20), "2000")  # 10日
    await _invoice(db_session, cid, p2.partner_id, "INV-3", date(2026, 1, 20), "5000")  # 161日
    await _invoice(db_session, cid, p2.partner_id, "INV-4", date(2026, 1, 20), "9999", status="paid")

    invoices = (await db_session.execute(
        select(Invoice).where(
            Invoice.company_id == cid,
            Invoice.status.in_(ar_aging.OPEN_INVOICE_STATUSES),
        )
    )).scalars().all()
    partners = (await db_session.execute(
        select(Partner).where(Partner.company_id == cid)
    )).scalars().all()

    result = ar_aging.aggregate_aging(
        list(invoices), AS_OF, {p.partner_id: p.partner_name for p in partners}
    )

    # paid は対象外
    assert result["invoice_count"] == 3
    assert result["total"] == Decimal("8000")
    assert result["buckets"][ar_aging.BUCKET_NOT_DUE] == Decimal("1000")
    assert result["buckets"][ar_aging.BUCKET_1_30] == Decimal("2000")
    assert result["buckets"][ar_aging.BUCKET_OVER_90] == Decimal("5000")
    assert result["overdue_total"] == Decimal("7000")

    # 残高降順（小口商事5000 > 大口物産3000）
    assert [p.partner_name for p in result["partners"]] == ["小口商事", "大口物産"]
    assert result["partners"][0].oldest_days_overdue == 161


async def test_aging_scoped_to_company(db_session, seed_company):
    """他社の請求書が混入しないこと。"""
    cid = seed_company["company_id"]
    await _invoice(db_session, cid, None, "INV-OWN", date(2026, 6, 1), "1000")

    invoices = (await db_session.execute(
        select(Invoice).where(
            Invoice.company_id == cid,
            Invoice.status.in_(ar_aging.OPEN_INVOICE_STATUSES),
        )
    )).scalars().all()
    result = ar_aging.aggregate_aging(list(invoices), AS_OF)
    assert result["total"] == Decimal("1000")
    assert all(i.company_id == cid for i in invoices)
