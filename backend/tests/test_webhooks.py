import pytest

from app.services.webhook_service import (
    BACKOFF_MAX_SECONDS,
    build_event_payload,
    compute_backoff_seconds,
    event_matches,
    serialize_payload,
    sign_payload,
    verify_signature,
)


class TestSigning:
    def test_sign_is_deterministic_and_prefixed(self):
        body = b'{"a":1}'
        sig1 = sign_payload("secret", body)
        sig2 = sign_payload("secret", body)
        assert sig1 == sig2
        assert sig1.startswith("sha256=")

    def test_different_secret_changes_signature(self):
        body = b'{"a":1}'
        assert sign_payload("secret-a", body) != sign_payload("secret-b", body)

    def test_verify_signature_roundtrip(self):
        body = serialize_payload({"event": "test", "n": 1})
        sig = sign_payload("s3cr3t!!", body)
        assert verify_signature("s3cr3t!!", body, sig) is True

    def test_verify_signature_rejects_tampered(self):
        body = serialize_payload({"amount": 100})
        sig = sign_payload("s3cr3t!!", body)
        tampered = serialize_payload({"amount": 999})
        assert verify_signature("s3cr3t!!", tampered, sig) is False

    def test_verify_signature_rejects_empty(self):
        body = serialize_payload({"x": 1})
        assert verify_signature("s3cr3t!!", body, "") is False


class TestSerializePayload:
    def test_key_order_is_deterministic(self):
        a = serialize_payload({"b": 2, "a": 1})
        b = serialize_payload({"a": 1, "b": 2})
        assert a == b

    def test_japanese_not_escaped(self):
        body = serialize_payload({"title": "現金売上"})
        assert "現金売上".encode("utf-8") in body


class TestBackoff:
    def test_exponential_growth(self):
        assert compute_backoff_seconds(1) == 60
        assert compute_backoff_seconds(2) == 120
        assert compute_backoff_seconds(3) == 240
        assert compute_backoff_seconds(4) == 480
        assert compute_backoff_seconds(5) == 960

    def test_capped_at_max(self):
        assert compute_backoff_seconds(20) == BACKOFF_MAX_SECONDS

    def test_zero_or_negative_treated_as_first_attempt(self):
        assert compute_backoff_seconds(0) == 60
        assert compute_backoff_seconds(-3) == 60


class TestEventMatches:
    def test_wildcard_matches_everything(self):
        assert event_matches(["*"], "notification.approval") is True
        assert event_matches(["*"], "journal.posted") is True

    def test_exact_match(self):
        assert event_matches(["journal.posted"], "journal.posted") is True
        assert event_matches(["journal.posted"], "journal.voided") is False

    def test_prefix_wildcard(self):
        assert event_matches(["notification.*"], "notification.approval") is True
        assert event_matches(["notification.*"], "notification.ai") is True
        assert event_matches(["notification.*"], "journal.posted") is False

    def test_empty_subscription_matches_nothing(self):
        assert event_matches([], "notification.approval") is False
        assert event_matches(None, "notification.approval") is False

    def test_multiple_patterns(self):
        subs = ["journal.posted", "notification.*"]
        assert event_matches(subs, "journal.posted") is True
        assert event_matches(subs, "notification.tax") is True
        assert event_matches(subs, "payroll.run") is False


class TestBuildEventPayload:
    def test_structure(self):
        payload = build_event_payload(
            "notification.approval",
            {"title": "承認依頼"},
            event_id="evt-1",
            occurred_at="2026-07-08T00:00:00+00:00",
        )
        assert payload["event_id"] == "evt-1"
        assert payload["event_type"] == "notification.approval"
        assert payload["occurred_at"] == "2026-07-08T00:00:00+00:00"
        assert payload["data"]["title"] == "承認依頼"
