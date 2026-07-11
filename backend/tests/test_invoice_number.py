import pytest

from app.services.invoice_number import (
    compute_check_digit,
    is_valid_corporate_number,
    is_valid_registration_number,
    normalize,
)


def _valid_corporate(base12: str) -> str:
    """基礎番号12桁から検査用数字を付けた正しい13桁法人番号を作る。"""
    return f"{compute_check_digit(base12)}{base12}"


class TestNormalize:
    def test_strips_spaces_and_hyphens(self):
        assert normalize(" T1234-5678-90123 ") == "T1234567890123"

    def test_none(self):
        assert normalize(None) == ""


class TestCheckDigit:
    def test_deterministic(self):
        assert compute_check_digit("123456789012") == compute_check_digit("123456789012")

    def test_range(self):
        assert 0 <= compute_check_digit("000000000001") <= 9

    def test_requires_12_digits(self):
        with pytest.raises(ValueError):
            compute_check_digit("123")


class TestCorporateNumber:
    def test_valid_roundtrip(self):
        num = _valid_corporate("123456789012")
        assert is_valid_corporate_number(num) is True

    def test_wrong_check_digit_rejected(self):
        num = _valid_corporate("123456789012")
        bad = str((int(num[0]) + 1) % 10) + num[1:]
        assert is_valid_corporate_number(bad) is False

    def test_non_digit_rejected(self):
        assert is_valid_corporate_number("12345678901X2") is False

    def test_wrong_length_rejected(self):
        assert is_valid_corporate_number("12345") is False


class TestRegistrationNumber:
    def test_valid(self):
        num = "T" + _valid_corporate("987654321098")
        assert is_valid_registration_number(num) is True

    def test_valid_with_formatting(self):
        num = "T" + _valid_corporate("987654321098")
        assert is_valid_registration_number(f" {num[:5]}-{num[5:]} ") is True

    def test_missing_t_prefix_rejected(self):
        num = _valid_corporate("987654321098")  # 13 digits, no T
        assert is_valid_registration_number(num) is False

    def test_bad_check_digit_rejected(self):
        base = _valid_corporate("987654321098")
        bad = "T" + str((int(base[0]) + 1) % 10) + base[1:]
        assert is_valid_registration_number(bad) is False

    def test_none_and_empty(self):
        assert is_valid_registration_number(None) is False
        assert is_valid_registration_number("") is False
