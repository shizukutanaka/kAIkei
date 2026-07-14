import pytest

from app.services.webhook_service import (
    BACKOFF_MAX_SECONDS,
    build_event_payload,
    compute_backoff_seconds,
    event_matches,
    is_unsafe_ip,
    resolve_and_check_safe,
    serialize_payload,
    sign_payload,
    validate_webhook_url_scheme,
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

class TestTimestampedSigning:
    """リプレイ防止（タイムスタンプ込み署名）のテスト。"""

    def test_timestamp_changes_signature(self):
        body = serialize_payload({"a": 1})
        assert sign_payload("s", body) != sign_payload("s", body, 1700000000)
        assert sign_payload("s", body, 1700000000) != sign_payload("s", body, 1700000001)

    def test_verify_within_window(self):
        body = serialize_payload({"a": 1})
        ts = 1700000000
        sig = sign_payload("s", body, ts)
        assert verify_signature("s", body, sig, timestamp=ts, now=ts + 200) is True

    def test_verify_rejects_expired(self):
        body = serialize_payload({"a": 1})
        ts = 1700000000
        sig = sign_payload("s", body, ts)
        assert verify_signature("s", body, sig, timestamp=ts, now=ts + 301) is False

    def test_verify_rejects_future_timestamp(self):
        body = serialize_payload({"a": 1})
        now = 1700000000
        ts = now + 301
        sig = sign_payload("s", body, ts)
        assert verify_signature("s", body, sig, timestamp=ts, now=now) is False

    def test_verify_rejects_mismatched_timestamp(self):
        body = serialize_payload({"a": 1})
        ts = 1700000000
        sig = sign_payload("s", body, ts)
        # ウィンドウ内でもタイムスタンプが署名と食い違えば拒否される
        assert verify_signature("s", body, sig, timestamp=ts + 1, now=ts + 2) is False


class TestIsUnsafeIp:
    def test_public_ip_is_safe(self):
        assert is_unsafe_ip("8.8.8.8") is False
        assert is_unsafe_ip("1.1.1.1") is False

    def test_private_ranges_unsafe(self):
        assert is_unsafe_ip("10.0.0.1") is True
        assert is_unsafe_ip("192.168.1.1") is True
        assert is_unsafe_ip("172.16.0.1") is True

    def test_loopback_unsafe(self):
        assert is_unsafe_ip("127.0.0.1") is True
        assert is_unsafe_ip("::1") is True

    def test_cloud_metadata_ip_unsafe(self):
        # 169.254.169.254 はAWS/GCP/Azure等のインスタンスメタデータエンドポイント
        assert is_unsafe_ip("169.254.169.254") is True

    def test_unspecified_and_multicast_unsafe(self):
        assert is_unsafe_ip("0.0.0.0") is True
        assert is_unsafe_ip("224.0.0.1") is True

    def test_unparseable_treated_as_unsafe(self):
        assert is_unsafe_ip("not-an-ip") is True


class TestValidateWebhookUrlScheme:
    def test_http_and_https_allowed(self):
        assert validate_webhook_url_scheme("https://example.com/hook") is None
        assert validate_webhook_url_scheme("http://example.com/hook") is None

    def test_other_schemes_rejected(self):
        assert validate_webhook_url_scheme("file:///etc/passwd") is not None
        assert validate_webhook_url_scheme("ftp://example.com") is not None
        assert validate_webhook_url_scheme("gopher://example.com") is not None

    def test_missing_hostname_rejected(self):
        assert validate_webhook_url_scheme("https:///path") is not None


class _FakeResolver:
    """asyncio getaddrinfo互換の戻り値形状を模したフェイク名前解決。"""

    def __init__(self, addresses: list[str]):
        self._addresses = addresses

    async def __call__(self, hostname, port):
        return [(2, 1, 6, "", (addr, port)) for addr in self._addresses]


class TestResolveAndCheckSafe:
    async def test_public_address_allowed(self):
        resolver = _FakeResolver(["8.8.8.8"])
        assert await resolve_and_check_safe("https://example.com/hook", resolver=resolver) is None

    async def test_private_address_blocked(self):
        resolver = _FakeResolver(["10.0.0.5"])
        reason = await resolve_and_check_safe("https://internal.example/hook", resolver=resolver)
        assert reason is not None and "10.0.0.5" in reason

    async def test_metadata_address_blocked(self):
        resolver = _FakeResolver(["169.254.169.254"])
        reason = await resolve_and_check_safe("http://169.254.169.254/latest/meta-data/", resolver=resolver)
        assert reason is not None

    async def test_mixed_addresses_blocked_if_any_unsafe(self):
        # DNSラウンドロビンで複数アドレスが返る場合、1つでも危険なら拒否する
        resolver = _FakeResolver(["8.8.8.8", "127.0.0.1"])
        assert await resolve_and_check_safe("https://example.com/hook", resolver=resolver) is not None

    async def test_bad_scheme_rejected_without_resolving(self):
        called = False

        async def resolver(hostname, port):
            nonlocal called
            called = True
            return []

        reason = await resolve_and_check_safe("ftp://example.com", resolver=resolver)
        assert reason is not None
        assert called is False  # スキーム不正の時点で名前解決を試みない

    async def test_unresolvable_hostname_blocked(self):
        async def resolver(hostname, port):
            raise OSError("name resolution failed")

        reason = await resolve_and_check_safe("https://does-not-exist.invalid/hook", resolver=resolver)
        assert reason is not None
