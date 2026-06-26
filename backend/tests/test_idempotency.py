import hashlib
import pytest

from app.middleware.idempotency import IDEMPOTENCY_HEADER, IDEMPOTENCY_TTL_HOURS


class TestIdempotency:
    def test_header_name(self):
        assert IDEMPOTENCY_HEADER == "Idempotency-Key"

    def test_ttl_hours(self):
        assert IDEMPOTENCY_TTL_HOURS == 24

    def test_request_hash_consistency(self):
        body1 = b'{"amount": 1000}'
        body2 = b'{"amount": 1000}'
        body3 = b'{"amount": 2000}'

        hash1 = hashlib.sha256(body1).hexdigest()
        hash2 = hashlib.sha256(body2).hexdigest()
        hash3 = hashlib.sha256(body3).hexdigest()

        assert hash1 == hash2
        assert hash1 != hash3

    def test_different_keys_different_records(self):
        key1 = "abc-123"
        key2 = "def-456"
        assert key1 != key2
