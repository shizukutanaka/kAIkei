from datetime import date
from decimal import Decimal

from app.services.invoice_registration import InvoiceRegistrationService
from app.services.qualified_invoice_check import (
    QualifiedInvoiceCheckService,
    QualifiedInvoiceInput,
    QualifiedInvoiceLine,
)


def _valid_registration_number() -> str:
    base12 = "000012090001"
    total = 0
    for n, digit_char in enumerate(reversed(base12), start=1):
        weight = 1 if n % 2 == 1 else 2
        total += int(digit_char) * weight
    check_digit = 9 - (total % 9)
    return f"T{check_digit}{base12}"


def _valid_invoice() -> QualifiedInvoiceInput:
    return QualifiedInvoiceInput(
        issuer_name="株式会社テスト",
        registration_number=_valid_registration_number(),
        transaction_date=date(2025, 1, 15),
        recipient_name="株式会社取引先",
        line_items=[
            QualifiedInvoiceLine(description="商品A", tax_rate=Decimal("0.10")),
            QualifiedInvoiceLine(description="食品B", tax_rate=Decimal("0.08")),
        ],
        tax_by_rate={Decimal("0.10"): Decimal("100"), Decimal("0.08"): Decimal("80")},
    )


class TestQualifiedInvoiceCheckService:
    def test_valid_invoice(self):
        invoice = _valid_invoice()
        result = QualifiedInvoiceCheckService.check(invoice)

        assert result.is_valid is True
        assert result.missing_fields == []
        assert result.registration_number_valid is True
        assert InvoiceRegistrationService.validate(invoice.registration_number).check_digit_valid is True

    def test_bad_registration_number(self):
        invoice = _valid_invoice()
        invoice = QualifiedInvoiceInput(
            issuer_name=invoice.issuer_name,
            registration_number="T123",
            transaction_date=invoice.transaction_date,
            recipient_name=invoice.recipient_name,
            line_items=invoice.line_items,
            tax_by_rate=invoice.tax_by_rate,
        )
        result = QualifiedInvoiceCheckService.check(invoice)

        assert result.is_valid is False
        assert "registration_number" in result.missing_fields
        assert result.registration_number_valid is False

    def test_missing_transaction_date(self):
        invoice = _valid_invoice()
        invoice = QualifiedInvoiceInput(
            issuer_name=invoice.issuer_name,
            registration_number=invoice.registration_number,
            transaction_date=None,
            recipient_name=invoice.recipient_name,
            line_items=invoice.line_items,
            tax_by_rate=invoice.tax_by_rate,
        )
        result = QualifiedInvoiceCheckService.check(invoice)
        assert "transaction_date" in result.missing_fields
        assert result.is_valid is False

    def test_empty_line_items(self):
        invoice = _valid_invoice()
        invoice = QualifiedInvoiceInput(
            issuer_name=invoice.issuer_name,
            registration_number=invoice.registration_number,
            transaction_date=invoice.transaction_date,
            recipient_name=invoice.recipient_name,
            line_items=[],
            tax_by_rate=invoice.tax_by_rate,
        )
        result = QualifiedInvoiceCheckService.check(invoice)
        assert "line_items" in result.missing_fields
        assert result.is_valid is False

    def test_empty_description(self):
        invoice = _valid_invoice()
        invoice = QualifiedInvoiceInput(
            issuer_name=invoice.issuer_name,
            registration_number=invoice.registration_number,
            transaction_date=invoice.transaction_date,
            recipient_name=invoice.recipient_name,
            line_items=[QualifiedInvoiceLine(description="", tax_rate=Decimal("0.10"))],
            tax_by_rate={Decimal("0.10"): Decimal("100")},
        )
        result = QualifiedInvoiceCheckService.check(invoice)
        assert "line_items" in result.missing_fields
        assert result.is_valid is False

    def test_unsupported_rate(self):
        invoice = _valid_invoice()
        invoice = QualifiedInvoiceInput(
            issuer_name=invoice.issuer_name,
            registration_number=invoice.registration_number,
            transaction_date=invoice.transaction_date,
            recipient_name=invoice.recipient_name,
            line_items=[QualifiedInvoiceLine(description="商品A", tax_rate=Decimal("0.05"))],
            tax_by_rate={Decimal("0.05"): Decimal("50")},
        )
        result = QualifiedInvoiceCheckService.check(invoice)
        assert "tax_rate" in result.missing_fields
        assert result.is_valid is False

    def test_missing_tax_by_rate(self):
        invoice = _valid_invoice()
        invoice = QualifiedInvoiceInput(
            issuer_name=invoice.issuer_name,
            registration_number=invoice.registration_number,
            transaction_date=invoice.transaction_date,
            recipient_name=invoice.recipient_name,
            line_items=invoice.line_items,
            tax_by_rate={Decimal("0.10"): Decimal("100")},
        )
        result = QualifiedInvoiceCheckService.check(invoice)
        assert "tax_by_rate" in result.missing_fields
        assert result.is_valid is False

    def test_empty_recipient_name(self):
        invoice = _valid_invoice()
        invoice = QualifiedInvoiceInput(
            issuer_name=invoice.issuer_name,
            registration_number=invoice.registration_number,
            transaction_date=invoice.transaction_date,
            recipient_name="",
            line_items=invoice.line_items,
            tax_by_rate=invoice.tax_by_rate,
        )
        result = QualifiedInvoiceCheckService.check(invoice)
        assert "recipient_name" in result.missing_fields
        assert result.is_valid is False

    def test_multi_defect(self):
        invoice = QualifiedInvoiceInput(
            issuer_name="",
            registration_number="T123",
            transaction_date=None,
            recipient_name="",
            line_items=[],
            tax_by_rate={},
        )
        result = QualifiedInvoiceCheckService.check(invoice)
        assert result.is_valid is False
        assert result.missing_fields == [
            "issuer_name",
            "registration_number",
            "transaction_date",
            "line_items",
            "recipient_name",
        ]
