
from app.services.security_policy import (
    ip_allowed,
    is_locked_out,
    normalize_cidrs,
    validate_password_length,
)


class TestIpAllowed:
    def test_empty_cidrs_allows_all(self):
        assert ip_allowed("203.0.113.5", []) is True

    def test_ip_in_range(self):
        assert ip_allowed("192.168.1.50", ["192.168.1.0/24"]) is True

    def test_ip_outside_range(self):
        assert ip_allowed("10.0.0.1", ["192.168.1.0/24"]) is False

    def test_multiple_ranges(self):
        cidrs = ["192.168.1.0/24", "10.0.0.0/8"]
        assert ip_allowed("10.5.5.5", cidrs) is True
        assert ip_allowed("172.16.0.1", cidrs) is False

    def test_invalid_ip_rejected(self):
        assert ip_allowed("not-an-ip", ["0.0.0.0/0"]) is False

    def test_invalid_cidr_ignored(self):
        # 不正なCIDRは無視され、有効なものだけで判定される
        assert ip_allowed("192.168.1.5", ["bad-cidr", "192.168.1.0/24"]) is True

    def test_ipv6(self):
        assert ip_allowed("2001:db8::1", ["2001:db8::/32"]) is True

    def test_single_host_cidr(self):
        assert ip_allowed("203.0.113.7", ["203.0.113.7/32"]) is True
        assert ip_allowed("203.0.113.8", ["203.0.113.7/32"]) is False


class TestValidatePasswordLength:
    def test_meets_minimum(self):
        assert validate_password_length("abcdefgh", 8) is True

    def test_too_short(self):
        assert validate_password_length("abc", 8) is False

    def test_empty(self):
        assert validate_password_length("", 8) is False


class TestIsLockedOut:
    def test_at_threshold(self):
        assert is_locked_out(5, 5) is True

    def test_below_threshold(self):
        assert is_locked_out(4, 5) is False

    def test_above_threshold(self):
        assert is_locked_out(7, 5) is True


class TestNormalizeCidrs:
    def test_drops_invalid(self):
        assert normalize_cidrs(["192.168.1.0/24", "garbage"]) == ["192.168.1.0/24"]

    def test_normalizes_host_bits(self):
        # strict=False: ホストビットを含む表記も正規化される
        assert normalize_cidrs(["192.168.1.5/24"]) == ["192.168.1.0/24"]

    def test_empty(self):
        assert normalize_cidrs([]) == []
