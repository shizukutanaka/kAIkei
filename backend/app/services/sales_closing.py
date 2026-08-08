"""売上明細の締め集計から請求データ・売上計上仕訳・入金予定を生成する。

#84/#85 で入金消込と消込仕訳は自動化したが、その対象である**売掛金そのものは人が起票**していた。
締め日・支払サイト・税率が分かれば、締め集計から請求書1枚と仕訳は一意に決まるので、この工程も消せる。

    売上明細(得意先・売上日・税抜金額・税率)
      → 締め日で束ねる               (得意先ごとに 20日締/末日締 が異なる)
      → 税率ごとに1回だけ端数処理     (インボイスの要件)
      → (借) 売掛金 / (貸) 売上高・仮受消費税等
      → 入金予定日 = 支払サイト(翌月末等)＋銀行休業日調整

要点は**消費税の端数処理を明細ごとではなく請求書単位・税率ごとに1回行う**こと。
行ごとに切り捨てると請求書の税額と自社の計上額がズレ、相手方の仕入税額控除にも影響する
(105円×3行 @10%: 行ごと切捨=30円、請求書単位=31円)。

生成される請求データは `receivable_matching` の `invoices` にそのまま渡せる形にしてあり、
「請求 → 入金 → 消込 → 仕訳」が同じ ID で閉じる。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.invoice_tax import InvoiceTaxLine, InvoiceTaxService
from app.services.payment_terms import PaymentTermsService

ROLE_ACCOUNTS_RECEIVABLE = "accounts_receivable"
ROLE_SALES_REVENUE = "sales_revenue"
ROLE_CONSUMPTION_TAX_PAYABLE = "consumption_tax_payable"

DRAFT_SALES = "sales"

_ZERO = Decimal("0")


@dataclass(frozen=True)
class SalesLine:
    line_id: str
    customer_code: str
    customer_name: str
    sales_date: date
    amount: Decimal
    tax_rate: Decimal
    description: str = ""


@dataclass(frozen=True)
class BillingTerms:
    customer_code: str
    closing_day: int
    payment_month_offset: int = 1
    payment_day: int = 31
    adjustment: str = "next"


@dataclass(frozen=True)
class TaxBreakdown:
    tax_rate: Decimal
    taxable_base: Decimal
    tax: Decimal


@dataclass(frozen=True)
class SalesJournalLine:
    account_role: str
    debit: Decimal
    credit: Decimal
    tax_rate: Decimal | None = None


@dataclass(frozen=True)
class ClosedInvoice:
    invoice_id: str
    customer_code: str
    customer_name: str
    closing_date: date
    due_date: date
    line_ids: list[str]
    by_rate: list[TaxBreakdown]
    total_taxable: Decimal
    total_tax: Decimal
    total_amount: Decimal
    journal_lines: list[SalesJournalLine]
    total_debit: Decimal
    total_credit: Decimal


@dataclass(frozen=True)
class SalesClosingResult:
    invoices: list[ClosedInvoice]
    invoice_count: int
    total_taxable: Decimal
    total_tax: Decimal
    total_amount: Decimal
    balanced: bool


class SalesClosingService:
    """売上明細を締め、請求・仕訳・入金予定を確定する純粋サービス。"""

    @classmethod
    def close(
        cls,
        *,
        lines: list[SalesLine],
        terms: list[BillingTerms],
        holidays: set[date] | None = None,
    ) -> SalesClosingResult:
        terms_by_customer = {item.customer_code: item for item in terms}
        if len(terms_by_customer) != len(terms):
            raise ValueError("customer_code must be unique in terms")
        line_ids = [line.line_id for line in lines]
        if len(set(line_ids)) != len(line_ids):
            raise ValueError("line_id must be unique")

        grouped: dict[tuple[str, date], list[SalesLine]] = defaultdict(list)
        for line in lines:
            if line.amount < _ZERO:
                raise ValueError("amount must not be negative")
            term = terms_by_customer.get(line.customer_code)
            if term is None:
                raise ValueError(f"billing terms are missing for customer {line.customer_code}")
            closing_date = PaymentTermsService.compute_closing_date(
                line.sales_date,
                term.closing_day,
            )
            grouped[(line.customer_code, closing_date)].append(line)

        invoices: list[ClosedInvoice] = []
        for (customer_code, closing_date), group in sorted(
            grouped.items(),
            key=lambda item: (item[0][1], item[0][0]),
        ):
            term = terms_by_customer[customer_code]
            tax = InvoiceTaxService.compute_invoice_tax(
                [InvoiceTaxLine(amount=line.amount, tax_rate=line.tax_rate) for line in group],
            )
            due_date = PaymentTermsService.compute_payment_date(
                closing_date,
                term.closing_day,
                term.payment_month_offset,
                term.payment_day,
                holidays=holidays,
                adjustment=term.adjustment,
            )
            journal_lines = [
                SalesJournalLine(ROLE_ACCOUNTS_RECEIVABLE, tax.total_amount, _ZERO),
                *[
                    SalesJournalLine(
                        ROLE_SALES_REVENUE,
                        _ZERO,
                        breakdown.taxable_base,
                        tax_rate=breakdown.tax_rate,
                    )
                    for breakdown in tax.by_rate
                    if breakdown.taxable_base > _ZERO
                ],
                SalesJournalLine(ROLE_CONSUMPTION_TAX_PAYABLE, _ZERO, tax.total_tax),
            ]
            journal_lines = [
                line for line in journal_lines if line.debit > _ZERO or line.credit > _ZERO
            ]
            total_debit = sum((line.debit for line in journal_lines), _ZERO)
            total_credit = sum((line.credit for line in journal_lines), _ZERO)
            if total_debit != total_credit:
                raise ValueError(f"generated sales draft is unbalanced ({customer_code})")

            invoices.append(
                ClosedInvoice(
                    invoice_id=f"{closing_date:%Y%m%d}-{customer_code}",
                    customer_code=customer_code,
                    customer_name=group[0].customer_name,
                    closing_date=closing_date,
                    due_date=due_date,
                    line_ids=[line.line_id for line in group],
                    by_rate=[
                        TaxBreakdown(
                            tax_rate=breakdown.tax_rate,
                            taxable_base=breakdown.taxable_base,
                            tax=breakdown.tax,
                        )
                        for breakdown in tax.by_rate
                    ],
                    total_taxable=tax.total_taxable,
                    total_tax=tax.total_tax,
                    total_amount=tax.total_amount,
                    journal_lines=journal_lines,
                    total_debit=total_debit,
                    total_credit=total_credit,
                ),
            )

        return SalesClosingResult(
            invoices=invoices,
            invoice_count=len(invoices),
            total_taxable=sum((item.total_taxable for item in invoices), _ZERO),
            total_tax=sum((item.total_tax for item in invoices), _ZERO),
            total_amount=sum((item.total_amount for item in invoices), _ZERO),
            balanced=all(item.total_debit == item.total_credit for item in invoices),
        )
