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
        db_session, cid, tid, date_from=date(2026, 4, 1), date_to=date(2026, 4, 30),
        amount_min=Decimal("10000"), amount_max=Decimal("20000"), counterparty="カイケイ",
    )
    assert [d.archived_document_id for d in hit] == [doc.archived_document_id]

    # out-of-range search misses
    assert await document_archive.search_documents(db_session, cid, tid, amount_min=Decimal("50000")) == []

    # download returns identical bytes
    down = await document_archive.download_document(db_session, doc.archived_document_id, cid, tid)
    assert down is not None and down[1] == content

    # stored-copy verify (no re-upload) reports valid
    stored = await document_archive.verify_document(db_session, doc.archived_document_id, cid, tid)
    assert stored["is_valid"] is True

    # explicit tampered bytes report invalid
    tampered = await document_archive.verify_document(db_session, doc.archived_document_id, cid, tid, b"tampered")
    assert tampered["is_valid"] is False


async def test_supersede_retains_old_and_hides_it_from_search(db_session, seed_company, fake_store):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    old = await document_archive.archive_document(
        db_session, tenant_id=tid, company_id=cid, document_type="invoice",
        file_name="v1.pdf", file_bytes=b"version 1", transaction_date=date(2026, 4, 15),
        storage_path="c/v1.pdf", amount=Decimal("11000"), counterparty_name="カイケイ商事",
    )
    result = await document_archive.supersede_document(
        db_session, tenant_id=tid, company_id=cid, old_document_id=old.archived_document_id,
        document_type="invoice", file_name="v2.pdf", file_bytes=b"version 2",
        transaction_date=date(2026, 4, 15), storage_path="c/v2.pdf",
        amount=Decimal("11000"), counterparty_name="カイケイ商事",
    )
    assert result is not None
    old_after, new = result
    assert old_after.superseded_by_id == new.archived_document_id

    # default search returns only the current version
    current = await document_archive.search_documents(db_session, cid, tid)
    ids = {d.archived_document_id for d in current}
    assert new.archived_document_id in ids
    assert old.archived_document_id not in ids

    # include_superseded returns both (correction history preserved)
    all_versions = await document_archive.search_documents(db_session, cid, tid, include_superseded=True)
    assert len(all_versions) == 2

    # the old version is still downloadable (retained, not deleted)
    down = await document_archive.download_document(db_session, old.archived_document_id, cid, tid)
    assert down is not None and down[1] == b"version 1"


async def test_archive_rejects_company_from_another_tenant(db_session, seed_company, fake_store):
    """company_idが指定tenant_idに属していなければ登録を拒否する（テナント取り違え防止）。"""
    from app.models.models import Tenant

    cid = seed_company["company_id"]
    other_tenant = Tenant(tenant_name="Other Tenant", tenant_code="OTHER")
    db_session.add(other_tenant)
    await db_session.flush()

    with pytest.raises(document_archive.CompanyNotFoundError):
        await document_archive.archive_document(
            db_session, tenant_id=other_tenant.tenant_id, company_id=cid, document_type="invoice",
            file_name="forged.pdf", file_bytes=b"forged", transaction_date=date(2026, 4, 15),
            storage_path="forged/forged.pdf",
        )


async def test_cross_tenant_read_is_isolated(db_session, seed_company, fake_store):
    """他テナントのtenant_idでは、正しいcompany_idを知っていても証憑を読めない。"""
    from app.models.models import Tenant

    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    doc = await document_archive.archive_document(
        db_session, tenant_id=tid, company_id=cid, document_type="invoice",
        file_name="secret.pdf", file_bytes=b"secret", transaction_date=date(2026, 4, 15),
        storage_path="c/secret.pdf",
    )

    other_tenant = Tenant(tenant_name="Attacker Tenant", tenant_code="ATTACKER")
    db_session.add(other_tenant)
    await db_session.flush()

    assert await document_archive.get_document(db_session, doc.archived_document_id, cid, other_tenant.tenant_id) is None
    assert await document_archive.download_document(db_session, doc.archived_document_id, cid, other_tenant.tenant_id) is None
    assert await document_archive.verify_document(db_session, doc.archived_document_id, cid, other_tenant.tenant_id) is None
    assert await document_archive.search_documents(db_session, cid, other_tenant.tenant_id) == []


async def test_supersede_rejects_document_from_another_tenant(db_session, seed_company, fake_store):
    """他テナントのdocument_idを指定してsupersedeしても対象が見つからない（乗っ取り防止）。"""
    from app.models.models import Tenant

    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    victim_doc = await document_archive.archive_document(
        db_session, tenant_id=tid, company_id=cid, document_type="invoice",
        file_name="victim.pdf", file_bytes=b"victim", transaction_date=date(2026, 4, 15),
        storage_path="c/victim.pdf",
    )

    attacker_tenant = Tenant(tenant_name="Attacker Tenant", tenant_code="ATTACKER2")
    db_session.add(attacker_tenant)
    await db_session.flush()

    result = await document_archive.supersede_document(
        db_session, tenant_id=attacker_tenant.tenant_id, company_id=cid,
        old_document_id=victim_doc.archived_document_id, document_type="invoice",
        file_name="forged.pdf", file_bytes=b"forged", transaction_date=date(2026, 4, 15),
        storage_path="c/forged.pdf",
    )
    assert result is None
