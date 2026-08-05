from datetime import date
from decimal import Decimal

import pytest

from app.schemas.schemas import SalesClosingResponse
from app.services.sales_closing import (
    ROLE_ACCOUNTS_RECEIVABLE,
    ROLE_CONSUMPTION_TAX_PAYABLE,
    ROLE_SALES_REVENUE,
    BillingTerms,
    SalesClosingService,
    SalesLine,
)

STANDARD = Decimal("0.10")
REDUCED = Decimal("0.08")


def _line(line_id: str, amount: str, sales_date: str, *, customer: str = "C1", rate: Decimal = STANDARD) -> SalesLine:
    return SalesLine(
        line_id=line_id,
        customer_code=customer,
        customer_name=f"{customer}商事",
        sales_date=date.fromisoformat(sales_date),
        amount=Decimal(amount),
        tax_rate=rate,
    )


def _terms(customer: str = "C1", *, closing_day: int = 31, offset: int = 1, payment_day: int = 31) -> BillingTerms:
    return BillingTerms(
        customer_code=customer,
        closing_day=closing_day,
        payment_month_offset=offset,
        payment_day=payment_day,
    )


def _credit(invoice, role: str) -> Decimal:
    return sum(
        (line.credit for line in invoice.journal_lines if line.account_role == role),
        Decimal("0"),
    )


def test_month_end_closing_creates_one_invoice_per_customer():
    result = SalesClosingService.close(
        lines=[_line("L1", "100000", "2025-08-05"), _line("L2", "50000", "2025-08-20")],
        terms=[_terms()],
    )
    assert result.invoice_count == 1
    invoice = result.invoices[0]
    assert invoice.closing_date == date(2025, 8, 31)
    assert invoice.total_taxable == Decimal("150000")
    assert invoice.total_tax == Decimal("15000")
    assert invoice.total_amount == Decimal("165000")
    assert invoice.line_ids == ["L1", "L2"]


def test_tax_rounding_is_per_invoice_not_per_line():
    # 105 x 3 @10%: 行ごと切捨=30、請求書単位=31 (インボイスの端数処理)
    result = SalesClosingService.close(
        lines=[_line(f"L{i}", "105", "2025-08-05") for i in range(3)],
        terms=[_terms()],
    )
    invoice = result.invoices[0]
    assert invoice.total_taxable == Decimal("315")
    assert invoice.total_tax == Decimal("31")
    assert invoice.total_amount == Decimal("346")


def test_mixed_rates_are_broken_down_and_rounded_separately():
    result = SalesClosingService.close(
        lines=[
            _line("L1", "100000", "2025-08-05"),
            _line("L2", "50000", "2025-08-06", rate=REDUCED),
        ],
        terms=[_terms()],
    )
    invoice = result.invoices[0]
    assert [(b.tax_rate, b.taxable_base, b.tax) for b in invoice.by_rate] == [
        (REDUCED, Decimal("50000"), Decimal("4000")),
        (STANDARD, Decimal("100000"), Decimal("10000")),
    ]
    assert invoice.total_tax == Decimal("14000")
    assert _credit(invoice, ROLE_SALES_REVENUE) == Decimal("150000")
    assert _credit(invoice, ROLE_CONSUMPTION_TAX_PAYABLE) == Decimal("14000")


def test_journal_is_balanced_with_receivable_at_tax_inclusive_total():
    result = SalesClosingService.close(
        lines=[_line("L1", "100000", "2025-08-05")],
        terms=[_terms()],
    )
    invoice = result.invoices[0]
    debit = sum(
        (line.debit for line in invoice.journal_lines if line.account_role == ROLE_ACCOUNTS_RECEIVABLE),
        Decimal("0"),
    )
    assert debit == Decimal("110000")
    assert invoice.total_debit == invoice.total_credit == Decimal("110000")
    assert result.balanced is True


def test_closing_day_20_splits_into_two_invoices():
    result = SalesClosingService.close(
        lines=[_line("L1", "100000", "2025-08-15"), _line("L2", "70000", "2025-08-25")],
        terms=[_terms(closing_day=20)],
    )
    assert [i.closing_date for i in result.invoices] == [date(2025, 8, 20), date(2025, 9, 20)]
    assert [i.total_amount for i in result.invoices] == [Decimal("110000"), Decimal("77000")]


def test_due_date_follows_payment_terms_and_skips_bank_holiday():
    # 8月末締 → 翌月末払。2025-09-30は火曜だが休業日指定で翌営業日へ
    result = SalesClosingService.close(
        lines=[_line("L1", "100000", "2025-08-05")],
        terms=[_terms()],
        holidays={date(2025, 9, 30)},
    )
    assert result.invoices[0].due_date == date(2025, 10, 1)


def test_due_date_skips_weekend():
    # 2025-11-30 は日曜 → 12/1(月)
    result = SalesClosingService.close(
        lines=[_line("L1", "100000", "2025-10-05")],
        terms=[_terms()],
    )
    assert result.invoices[0].due_date == date(2025, 12, 1)


def test_invoices_are_separated_by_customer():
    result = SalesClosingService.close(
        lines=[
            _line("L1", "100000", "2025-08-05"),
            _line("L2", "200000", "2025-08-05", customer="C2"),
        ],
        terms=[_terms(), _terms("C2")],
    )
    assert result.invoice_count == 2
    assert {i.customer_code for i in result.invoices} == {"C1", "C2"}
    assert result.total_amount == Decimal("330000")


def test_invoice_id_is_deterministic_and_usable_for_matching():
    result = SalesClosingService.close(
        lines=[_line("L1", "100000", "2025-08-05")],
        terms=[_terms()],
    )
    assert result.invoices[0].invoice_id == "20250831-C1"


def test_missing_terms_rejected():
    with pytest.raises(ValueError, match="billing terms"):
        SalesClosingService.close(lines=[_line("L1", "100000", "2025-08-05")], terms=[])


def test_invalid_input_rejected():
    with pytest.raises(ValueError, match="line_id"):
        SalesClosingService.close(
            lines=[_line("L1", "100", "2025-08-05"), _line("L1", "200", "2025-08-06")],
            terms=[_terms()],
        )
    with pytest.raises(ValueError, match="customer_code"):
        SalesClosingService.close(
            lines=[_line("L1", "100", "2025-08-05")],
            terms=[_terms(), _terms()],
        )
    with pytest.raises(ValueError, match="amount"):
        SalesClosingService.close(
            lines=[_line("L1", "-100", "2025-08-05")],
            terms=[_terms()],
        )
    with pytest.raises(ValueError, match="tax_rate"):
        SalesClosingService.close(
            lines=[_line("L1", "100", "2025-08-05", rate=Decimal("0.05"))],
            terms=[_terms()],
        )


def test_no_lines_produces_no_invoices():
    result = SalesClosingService.close(lines=[], terms=[_terms()])
    assert result.invoice_count == 0
    assert result.total_amount == Decimal("0")
    assert result.balanced is True


def test_response_schema_serializes_dataclass():
    result = SalesClosingService.close(
        lines=[_line("L1", "100000", "2025-08-05")],
        terms=[_terms()],
    )
    payload = SalesClosingResponse.model_validate(result)
    assert payload.invoices[0].total_amount == Decimal("110000")
    assert payload.invoices[0].journal_lines[0].account_role == ROLE_ACCOUNTS_RECEIVABLE
