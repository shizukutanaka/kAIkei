"""電子帳簿保存法（電帳法）証憑アーカイブサービス（フェーズ2）。

証憑ファイルをSHA-256ハッシュ付きで登録し、電帳法が要求する検索3軸
（取引年月日・取引金額・取引先）による検索と、改ざん検知（ハッシュ再計算）を提供する。

ハッシュ計算・整合性検証・検索一致判定の中核はDB非依存の純粋関数として切り出す。
"""
import hashlib
import logging
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ArchivedDocument

logger = logging.getLogger(__name__)


# --- 純粋関数（DB非依存・テスト可能） ---------------------------------------

def compute_file_hash(file_bytes: bytes) -> str:
    """ファイルのSHA-256ハッシュ（16進）を計算する。"""
    return hashlib.sha256(file_bytes).hexdigest()


def verify_integrity(file_bytes: bytes, expected_hash: str) -> bool:
    """ファイルが登録時のハッシュと一致するか（改ざんされていないか）検証する。"""
    return compute_file_hash(file_bytes) == (expected_hash or "").lower()


def matches_search(
    transaction_date: date,
    amount: Decimal | None,
    counterparty_name: str | None,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    counterparty: str | None = None,
) -> bool:
    """電帳法の検索3軸（日付範囲・金額範囲・取引先部分一致）で一致判定する。"""
    if date_from is not None and transaction_date < date_from:
        return False
    if date_to is not None and transaction_date > date_to:
        return False
    if amount_min is not None and (amount is None or amount < amount_min):
        return False
    if amount_max is not None and (amount is None or amount > amount_max):
        return False
    if counterparty:
        if not counterparty_name or counterparty not in counterparty_name:
            return False
    return True


# --- 非同期サービス（DB依存） ------------------------------------------------

async def archive_document(
    db: AsyncSession,
    tenant_id: UUID,
    company_id: UUID,
    document_type: str,
    file_name: str,
    file_bytes: bytes,
    transaction_date: date,
    storage_path: str,
    amount: Decimal | None = None,
    counterparty_name: str | None = None,
    mime_type: str | None = None,
    linked_journal_header_id: UUID | None = None,
    registered_by: UUID | None = None,
) -> ArchivedDocument:
    """証憑ファイルのメタデータをSHA-256ハッシュ付きで登録する。"""
    document = ArchivedDocument(
        tenant_id=tenant_id,
        company_id=company_id,
        document_type=document_type,
        file_name=file_name,
        file_hash=compute_file_hash(file_bytes),
        file_size=len(file_bytes),
        mime_type=mime_type,
        storage_path=storage_path,
        transaction_date=transaction_date,
        amount=amount,
        counterparty_name=counterparty_name,
        linked_journal_header_id=linked_journal_header_id,
        registered_by=registered_by,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document


async def search_documents(
    db: AsyncSession,
    company_id: UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    counterparty: str | None = None,
    limit: int = 100,
) -> list[ArchivedDocument]:
    """電帳法の検索3軸で証憑を検索する。"""
    conditions = [ArchivedDocument.company_id == company_id]
    if date_from is not None:
        conditions.append(ArchivedDocument.transaction_date >= date_from)
    if date_to is not None:
        conditions.append(ArchivedDocument.transaction_date <= date_to)
    if amount_min is not None:
        conditions.append(ArchivedDocument.amount >= amount_min)
    if amount_max is not None:
        conditions.append(ArchivedDocument.amount <= amount_max)
    if counterparty:
        conditions.append(ArchivedDocument.counterparty_name.ilike(f"%{counterparty}%"))
    result = await db.execute(
        select(ArchivedDocument)
        .where(*conditions)
        .order_by(ArchivedDocument.transaction_date.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_document(
    db: AsyncSession, document_id: UUID, company_id: UUID
) -> ArchivedDocument | None:
    """証憑を1件取得する。"""
    result = await db.execute(
        select(ArchivedDocument).where(
            ArchivedDocument.archived_document_id == document_id,
            ArchivedDocument.company_id == company_id,
        )
    )
    return result.scalar_one_or_none()


async def verify_document(
    db: AsyncSession, document_id: UUID, company_id: UUID, file_bytes: bytes
) -> dict | None:
    """アップロードし直したファイルが登録時ハッシュと一致するか検証する。"""
    document = await get_document(db, document_id, company_id)
    if document is None:
        return None
    ok = verify_integrity(file_bytes, document.file_hash)
    return {
        "archived_document_id": str(document.archived_document_id),
        "is_valid": ok,
        "expected_hash": document.file_hash,
        "actual_hash": compute_file_hash(file_bytes),
    }
