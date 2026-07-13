import base64

import pytest

from app.services.mfa import (
    build_otpauth_uri,
    generate_totp_secret,
    totp_code,
    verify_totp,
)

# RFC 6238 Appendix B のテストベクター（SHA-1）。8桁の期待値の下6桁で検証する。
RFC6238_SECRET = base64.b32encode(b"12345678901234567890").decode("ascii")
RFC6238_VECTORS = [
    (59, "287082"),
    (1111111109, "081804"),
    (1111111111, "050471"),
    (1234567890, "005924"),
    (2000000000, "279037"),
    (20000000000, "353130"),
]


class TestTotpCode:
    @pytest.mark.parametrize("timestamp,expected", RFC6238_VECTORS)
    def test_rfc6238_vectors(self, timestamp, expected):
        assert totp_code(RFC6238_SECRET, timestamp) == expected

    def test_zero_padded(self):
        # 1234567890 → 005924: 先頭ゼロが保持されること
        assert totp_code(RFC6238_SECRET, 1234567890) == "005924"


class TestVerifyTotp:
    def test_accepts_current_code(self):
        assert verify_totp(RFC6238_SECRET, "287082", 59) is True

    def test_accepts_adjacent_window(self):
        # T=59 のコードは T=89（次ステップ）でも window=1 で受理される
        assert verify_totp(RFC6238_SECRET, "287082", 89, window=1) is True

    def test_rejects_outside_window(self):
        assert verify_totp(RFC6238_SECRET, "287082", 59 + 90, window=1) is False

    def test_rejects_wrong_code(self):
        assert verify_totp(RFC6238_SECRET, "000000", 59) is False

    def test_rejects_malformed_code(self):
        assert verify_totp(RFC6238_SECRET, "12345", 59) is False
        assert verify_totp(RFC6238_SECRET, "abcdef", 59) is False

    def test_rejects_invalid_secret(self):
        assert verify_totp("!!!not-base32!!!", "287082", 59) is False

    def test_accepts_code_with_spaces(self):
        assert verify_totp(RFC6238_SECRET, "287 082", 59) is True


class TestGenerateTotpSecret:
    def test_is_valid_base32_and_unique(self):
        s1, s2 = generate_totp_secret(), generate_totp_secret()
        assert s1 != s2
        assert len(base64.b32decode(s1 + "=" * (-len(s1) % 8))) == 20

    def test_roundtrip_with_totp(self):
        secret = generate_totp_secret()
        code = totp_code(secret, 1234567890)
        assert verify_totp(secret, code, 1234567890) is True


class TestBuildOtpauthUri:
    def test_structure(self):
        uri = build_otpauth_uri("ABC234", "user@example.com")
        assert uri.startswith("otpauth://totp/kAIkei:user%40example.com?")
        assert "secret=ABC234" in uri
        assert "issuer=kAIkei" in uri
        assert "digits=6" in uri
        assert "period=30" in uri
