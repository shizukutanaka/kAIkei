from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ArchivedDocument


class DocumentArchiveService:
    def __init__(self, storage_root: Path | None = None) -> None:
        self.storage_root = storage_root or Path(__file__).resolve().parents[2] / "storage" / "documents"

    @staticmethod
    def compute_hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _relative_path(self, company_id: UUID, document_id: UUID, extension: str) -> Path:
        return Path(str(company_id)) / f"{document_id}.{extension}"

    async def archive(
        self,
        db: AsyncSession,
        *,
        company_id: UUID,
        file: UploadFile,
        transaction_date,
        transaction_amount,
        counterparty_name: str,
        document_type: str,
        created_by: UUID,
    ) -> ArchivedDocument:
        content = await file.read()
        file_hash = self.compute_hash(content)
        existing = await db.execute(
            select(ArchivedDocument).where(
                ArchivedDocument.company_id == company_id,
                ArchivedDocument.file_hash == file_hash,
                ArchivedDocument.is_deleted == False,  # noqa: E712
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Document already archived")

        extension = (Path(file.filename or "document.bin").suffix or ".bin").lstrip(".").lower()
        document_id = uuid4()
        relative = self._relative_path(company_id, document_id, extension)
        absolute = self.storage_root / relative
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(content)

        archived = ArchivedDocument(
            document_id=document_id,
            company_id=company_id,
            file_path=str(relative).replace("\\", "/"),
            file_extension=extension,
            file_hash=file_hash,
            file_size=len(content),
            transaction_date=transaction_date,
            transaction_amount=transaction_amount,
            counterparty_name=counterparty_name,
            document_type=document_type,
            created_by=created_by,
        )
        db.add(archived)
        await db.flush()
        await db.refresh(archived)
        return archived

    async def search(
        self,
        db: AsyncSession,
        *,
        company_id: UUID,
        transaction_date_from=None,
        transaction_date_to=None,
        amount_min=None,
        amount_max=None,
        counterparty_name: str | None = None,
        document_type: str | None = None,
    ) -> list[ArchivedDocument]:
        stmt = select(ArchivedDocument).where(
            ArchivedDocument.company_id == company_id,
            ArchivedDocument.is_deleted == False,  # noqa: E712
        )
        if transaction_date_from is not None:
            stmt = stmt.where(ArchivedDocument.transaction_date >= transaction_date_from)
        if transaction_date_to is not None:
            stmt = stmt.where(ArchivedDocument.transaction_date <= transaction_date_to)
        if amount_min is not None:
            stmt = stmt.where(ArchivedDocument.transaction_amount >= amount_min)
        if amount_max is not None:
            stmt = stmt.where(ArchivedDocument.transaction_amount <= amount_max)
        if counterparty_name:
            stmt = stmt.where(ArchivedDocument.counterparty_name.ilike(f"%{counterparty_name}%"))
        if document_type:
            stmt = stmt.where(ArchivedDocument.document_type == document_type)
        stmt = stmt.order_by(ArchivedDocument.transaction_date.desc(), ArchivedDocument.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())
