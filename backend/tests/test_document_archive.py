import hashlib
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.services.document_archive import (
    build_storage_key,
    compute_file_hash,
    matches_search,
    verify_integrity,
)


class TestHashing:
    def test_hash_matches_hashlib(self):
        data = b"invoice content"
        assert compute_file_hash(data) == hashlib.sha256(data).hexdigest()

    def test_hash_is_deterministic(self):
        assert compute_file_hash(b"abc") == compute_file_hash(b"abc")

    def test_different_content_different_hash(self):
        assert compute_file_hash(b"a") != compute_file_hash(b"b")


class TestVerifyIntegrity:
    def test_valid_when_unchanged(self):
        data = b"receipt-2026-001"
        assert verify_integrity(data, compute_file_hash(data)) is True

    def test_invalid_when_tampered(self):
        original = b"amount: 10000"
        tampered = b"amount: 99999"
        assert verify_integrity(tampered, compute_file_hash(original)) is False

    def test_empty_expected_hash_is_invalid(self):
        assert verify_integrity(b"x", "") is False


class TestMatchesSearch:
    D = date(2026, 4, 15)

    def test_no_filters_matches(self):
        assert matches_search(self.D, Decimal("1000"), "カイケイ商事") is True

    def test_date_range(self):
        assert matches_search(self.D, None, None, date_from=date(2026, 4, 1), date_to=date(2026, 4, 30)) is True
        assert matches_search(self.D, None, None, date_from=date(2026, 5, 1)) is False
        assert matches_search(self.D, None, None, date_to=date(2026, 4, 1)) is False

    def test_amount_range(self):
        assert matches_search(self.D, Decimal("5000"), None, amount_min=Decimal("1000"), amount_max=Decimal("10000")) is True
        assert matches_search(self.D, Decimal("500"), None, amount_min=Decimal("1000")) is False
        assert matches_search(self.D, Decimal("20000"), None, amount_max=Decimal("10000")) is False

    def test_amount_filter_excludes_null_amount(self):
        assert matches_search(self.D, None, None, amount_min=Decimal("1000")) is False

    def test_counterparty_partial_match(self):
        assert matches_search(self.D, None, "株式会社カイケイ商事", counterparty="カイケイ") is True
        assert matches_search(self.D, None, "別の会社", counterparty="カイケイ") is False

    def test_counterparty_filter_excludes_null_name(self):
        assert matches_search(self.D, None, None, counterparty="カイケイ") is False

    def test_all_three_axes_combined(self):
        assert matches_search(
            self.D, Decimal("5000"), "カイケイ商事",
            date_from=date(2026, 4, 1), date_to=date(2026, 4, 30),
            amount_min=Decimal("1000"), amount_max=Decimal("10000"),
            counterparty="カイケイ",
        ) is True


class TestBuildStorageKey:
    TENANT = uuid.UUID("11111111-1111-1111-1111-111111111111")
    COMPANY = uuid.UUID("22222222-2222-2222-2222-222222222222")
    D = date(2026, 4, 15)

    def test_includes_tenant_company_and_date(self):
        key = build_storage_key(self.TENANT, self.COMPANY, self.D, "invoice.pdf")
        assert key.startswith(f"{self.TENANT}/{self.COMPANY}/2026-04-15/")
        assert key.endswith("_invoice.pdf")

    def test_two_calls_with_identical_inputs_never_collide(self):
        # 同一テナント・同一会社・同一日付・同一ファイル名の連続アップロードでも
        # ストレージキーが衝突しない（既存オブジェクトの上書き事故を防ぐ）。
        k1 = build_storage_key(self.TENANT, self.COMPANY, self.D, "invoice.pdf")
        k2 = build_storage_key(self.TENANT, self.COMPANY, self.D, "invoice.pdf")
        assert k1 != k2

    def test_sanitizes_path_traversal_in_filename(self):
        key = build_storage_key(self.TENANT, self.COMPANY, self.D, "../../etc/passwd")
        # スラッシュはすべて除去され、日付より後ろは単一セグメントの末尾ファイル名になる
        # （パス区切りが残らないため、経路逸脱に使えない）。
        tail = key.split(f"{self.D.isoformat()}/", 1)[1]
        assert "/" not in tail and "\\" not in tail

    def test_sanitizes_backslash(self):
        key = build_storage_key(self.TENANT, self.COMPANY, self.D, "..\\..\\windows\\win.ini")
        tail = key.split(f"{self.D.isoformat()}/", 1)[1]
        assert "\\" not in tail

    def test_empty_filename_falls_back_to_document(self):
        key = build_storage_key(self.TENANT, self.COMPANY, self.D, "")
        assert key.endswith("_document")
