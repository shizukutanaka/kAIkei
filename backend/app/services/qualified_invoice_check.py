from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.invoice_registration import InvoiceRegistrationService
from app.services.invoice_tax import ALLOWED_INVOICE_TAX_RATES


@dataclass(frozen=True)
class QualifiedInvoiceLine:
    description: str
    tax_rate: Decimal


@dataclass(frozen=True)
class QualifiedInvoiceInput:
    issuer_name: str
    registration_number: str
    transaction_date: date | None
    recipient_name: str
    line_items: list[QualifiedInvoiceLine]
    tax_by_rate: dict[Decimal, Decimal]


@dataclass(frozen=True)
class QualifiedInvoiceCheckResult:
    is_valid: bool
    missing_fields: list[str]
    registration_number_valid: bool


class QualifiedInvoiceCheckService:
    @staticmethod
    def _append_missing(missing_fields: list[str], key: str) -> None:
        if key not in missing_fields:
            missing_fields.append(key)

    @classmethod
    def check(cls, invoice: QualifiedInvoiceInput) -> QualifiedInvoiceCheckResult:
        missing_fields: list[str] = []

        issuer_name = invoice.issuer_name.strip()
        if not issuer_name:
            cls._append_missing(missing_fields, "issuer_name")

        registration_result = InvoiceRegistrationService.validate(invoice.registration_number)
        registration_number_valid = registration_result.format_valid and registration_result.check_digit_valid
        if not registration_number_valid:
            cls._append_missing(missing_fields, "registration_number")

        if invoice.transaction_date is None:
            cls._append_missing(missing_fields, "transaction_date")

        if not invoice.line_items:
            cls._append_missing(missing_fields, "line_items")
        else:
            distinct_rates: set[Decimal] = set()
            unsupported_rate_found = False
            invalid_description_found = False
            for line_item in invoice.line_items:
                if not line_item.description.strip():
                    invalid_description_found = True
                distinct_rates.add(line_item.tax_rate)
                if line_item.tax_rate not in ALLOWED_INVOICE_TAX_RATES:
                    unsupported_rate_found = True
            if invalid_description_found:
                cls._append_missing(missing_fields, "line_items")
            if unsupported_rate_found:
                cls._append_missing(missing_fields, "tax_rate")

            missing_tax_rate = any(rate not in invoice.tax_by_rate for rate in distinct_rates)
            if missing_tax_rate:
                cls._append_missing(missing_fields, "tax_by_rate")

        recipient_name = invoice.recipient_name.strip()
        if not recipient_name:
            cls._append_missing(missing_fields, "recipient_name")

        return QualifiedInvoiceCheckResult(
            is_valid=not missing_fields,
            missing_fields=missing_fields,
            registration_number_valid=registration_number_valid,
        )
