from datetime import date
from decimal import Decimal

import pytest

from app.services import document_archive

pytestmark = pytest.mark.db


async def test_archive_search_and_verify(db_session, seed_company):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    content = b"invoice INV-001 total 11000"
    doc = await document_archive.archive_document(
        db_session, tenant_id=tid, company_id=cid, document_type="invoice",
        file_name="inv-001.pdf", file_bytes=content, transaction_date=date(2026, 4, 15),
        storage_path="c/2026-04-15/inv-001.pdf", amount=Decimal("11000"), counterparty_name="カイケイ商事",
    )
    assert len(doc.file_hash) == 64

    # 3-axis search hits
    hit = await document_archive.search_documents(
        db_session, cid, date_from=date(2026, 4, 1), date_to=date(2026, 4, 30),
        amount_min=Decimal("10000"), amount_max=Decimal("20000"), counterparty="カイケイ",
    )
    assert [d.archived_document_id for d in hit] == [doc.archived_document_id]

    # out-of-range search misses
    miss = await document_archive.search_documents(db_session, cid, amount_min=Decimal("50000"))
    assert miss == []

    # integrity verify
    ok = await document_archive.verify_document(db_session, doc.archived_document_id, cid, content)
    assert ok["is_valid"] is True
    tampered = await document_archive.verify_document(db_session, doc.archived_document_id, cid, b"tampered")
    assert tampered["is_valid"] is False
