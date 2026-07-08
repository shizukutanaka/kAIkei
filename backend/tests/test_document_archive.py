from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.models.models import ArchivedDocument
from app.services.document_archive import DocumentArchiveService


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value


class _FakeDB:
    def __init__(self, execute_results: list[object]):
        self._execute_results = execute_results
        self.added: list[object] = []

    async def execute(self, _stmt):
        return _ScalarResult(self._execute_results.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None


class _FakeUploadFile:
    def __init__(self, content: bytes, filename: str):
        self._content = content
        self.filename = filename

    async def read(self) -> bytes:
        return self._content


class TestDocumentArchiveService:
    def test_compute_hash(self):
        assert DocumentArchiveService.compute_hash(b"hello") == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

    @pytest.mark.asyncio
    async def test_archive_writes_file_and_returns_document(self, tmp_path: Path):
        service = DocumentArchiveService(storage_root=tmp_path)
        db = _FakeDB([None])
        upload = _FakeUploadFile(b"pdf-bytes", "receipt.pdf")
        doc = await service.archive(
            db,
            company_id=uuid4(),
            file=upload,
            transaction_date=date(2026, 6, 30),
            transaction_amount=Decimal("12345.67"),
            counterparty_name="テスト商事",
            document_type="receipt",
            created_by=uuid4(),
        )
        assert isinstance(doc, ArchivedDocument)
        assert doc.file_extension == "pdf"
        assert doc.file_size == len(b"pdf-bytes")
        assert (tmp_path / doc.file_path).read_bytes() == b"pdf-bytes"
        assert len(db.added) == 1

    @pytest.mark.asyncio
    async def test_archive_duplicate_raises(self, tmp_path: Path):
        service = DocumentArchiveService(storage_root=tmp_path)
        db = _FakeDB([ArchivedDocument(document_id=uuid4(), company_id=uuid4(), file_path="x", file_extension="pdf", file_hash=DocumentArchiveService.compute_hash(b"dup"), file_size=3, transaction_date=date(2026, 6, 30), transaction_amount=Decimal("1"), counterparty_name="A", document_type="receipt", created_by=uuid4(), is_deleted=False)])
        upload = _FakeUploadFile(b"dup", "receipt.pdf")
        with pytest.raises(ValueError):
            await service.archive(
                db,
                company_id=uuid4(),
                file=upload,
                transaction_date=date(2026, 6, 30),
                transaction_amount=Decimal("1"),
                counterparty_name="A",
                document_type="receipt",
                created_by=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_search_filters_counterparty(self, tmp_path: Path):
        service = DocumentArchiveService(storage_root=tmp_path)
        item = ArchivedDocument(
            document_id=uuid4(),
            company_id=uuid4(),
            file_path="doc.pdf",
            file_extension="pdf",
            file_hash=DocumentArchiveService.compute_hash(b"abc"),
            file_size=3,
            transaction_date=date(2026, 6, 30),
            transaction_amount=Decimal("1000"),
            counterparty_name="東京電力",
            document_type="invoice",
            created_by=uuid4(),
            is_deleted=False,
        )
        db = _FakeDB([[item]])
        items = await service.search(db, company_id=item.company_id, counterparty_name="東京")
        assert len(items) == 1
        assert items[0].counterparty_name == "東京電力"
