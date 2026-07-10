from datetime import date
from decimal import Decimal

import pytest

from app.services import document_archive
from app.services.storage import InMemoryStorage

pytestmark = pytest.mark.db


@pytest.fixture
def fake_store(monkeypatch):
    store = InMemoryStorage()
    # archive_document / download_document default to storage_module.storage
    monkeypatch.setattr(document_archive.storage_module, "storage", store)
    return store


async def test_archive_search_download_and_verify(db_session, seed_company, fake_store):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    content = b"invoice INV-001 total 11000"
    doc = await document_archive.archive_document(
        db_session, tenant_id=tid, company_id=cid, document_type="invoice",
        file_name="inv-001.pdf", file_bytes=content, transaction_date=date(2026, 4, 15),
        storage_path="c/2026-04-15/inv-001.pdf", amount=Decimal("11000"), counterparty_name="カイケイ商事",
    )
    assert len(doc.file_hash) == 64
    # file bytes were actually stored
    assert await fake_store.get_object("c/2026-04-15/inv-001.pdf") == content

    # 3-axis search hits
    hit = await document_archive.search_documents(
        db_session, cid, date_from=date(2026, 4, 1), date_to=date(2026, 4, 30),
        amount_min=Decimal("10000"), amount_max=Decimal("20000"), counterparty="カイケイ",
    )
    assert [d.archived_document_id for d in hit] == [doc.archived_document_id]

    # out-of-range search misses
    assert await document_archive.search_documents(db_session, cid, amount_min=Decimal("50000")) == []

    # download returns identical bytes
    down = await document_archive.download_document(db_session, doc.archived_document_id, cid)
    assert down is not None and down[1] == content

    # stored-copy verify (no re-upload) reports valid
    stored = await document_archive.verify_document(db_session, doc.archived_document_id, cid)
    assert stored["is_valid"] is True

    # explicit tampered bytes report invalid
    tampered = await document_archive.verify_document(db_session, doc.archived_document_id, cid, b"tampered")
    assert tampered["is_valid"] is False
