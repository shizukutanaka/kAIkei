from app.services.invoice_registration import InvoiceRegistrationService


def _compute_check_digit_from_base12(base12: str) -> int:
    total = 0
    for n, digit_char in enumerate(reversed(base12), start=1):
        weight = 1 if n % 2 == 1 else 2
        total += int(digit_char) * weight
    return 9 - (total % 9)


class TestInvoiceRegistrationService:
    def test_valid_number_has_valid_format_and_check_digit(self):
        base12 = "000012090001"
        check_digit = _compute_check_digit_from_base12(base12)
        raw = f"T{check_digit}{base12}"

        result = InvoiceRegistrationService.validate(raw)

        assert result.input == raw
        assert result.normalized == raw
        assert result.format_valid is True
        assert result.check_digit_valid is True

    def test_wrong_check_digit_keeps_format_but_fails_checksum(self):
        base12 = "000012090001"
        check_digit = _compute_check_digit_from_base12(base12)
        wrong_check_digit = (check_digit + 1) % 10
        raw = f"T{wrong_check_digit}{base12}"

        result = InvoiceRegistrationService.validate(raw)

        assert result.format_valid is True
        assert result.check_digit_valid is False
        assert result.normalized == raw

    def test_format_failures(self):
        for raw in ["T123", "1234567890123", "TABCDEFGHIJKLM", ""]:
            result = InvoiceRegistrationService.validate(raw)
            assert result.format_valid is False
            assert result.normalized is None
            assert result.check_digit_valid is False

    def test_normalize_removes_spaces_hyphens_and_upcases(self):
        raw = "t-0000 1209-0001-2"

        normalized = InvoiceRegistrationService.normalize(raw)

        assert normalized == "T0000120900012"
        assert " " not in normalized
        assert "-" not in normalized
