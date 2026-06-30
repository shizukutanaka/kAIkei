"""イベント駆動仕訳ドラフト生成（純粋ロジック）。

業務イベント（売上計上・仕入/経費・入出金・減価償却 等）から、貸借一致した
仕訳ドラフトを決定論的に生成する。会社固有の勘定コードに依存しないよう、各行は
「勘定ロール（account_role）」で表現し、エンドポイント側が会社の勘定科目へ対応付ける。
消費税の按分は既存 TaxCalculator に委譲し、丸め規約を統一する。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from app.services.tax_calculator import TaxCalculator

# 勘定ロール（会社の勘定科目へマッピングする抽象キー）。
ROLE_ACCOUNTS_RECEIVABLE = "accounts_receivable"
ROLE_ACCOUNTS_PAYABLE = "accounts_payable"
ROLE_SALES = "sales"
ROLE_EXPENSE = "expense"
ROLE_CONSUMPTION_TAX_PAYABLE = "consumption_tax_payable"
ROLE_CONSUMPTION_TAX_RECEIVABLE = "consumption_tax_receivable"
ROLE_BANK_DEPOSIT = "bank_deposit"
ROLE_DEPRECIATION_EXPENSE = "depreciation_expense"
ROLE_ACCUMULATED_DEPRECIATION = "accumulated_depreciation"

_ZERO = Decimal("0")


@dataclass(frozen=True)
class JournalLineDraft:
    account_role: str
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class JournalDraft:
    event_type: str
    description: str
    lines: list[JournalLineDraft] = field(default_factory=list)

    @property
    def total_debit(self) -> Decimal:
        return sum((line.debit for line in self.lines), _ZERO)

    @property
    def total_credit(self) -> Decimal:
        return sum((line.credit for line in self.lines), _ZERO)


def _build_sales(amount: Decimal, tax_rate: Decimal, is_tax_inclusive: bool) -> JournalDraft:
    net, tax = TaxCalculator.calculate_tax(amount, tax_rate, is_tax_inclusive)
    return JournalDraft(
        event_type="sales",
        description="売上計上",
        lines=[
            JournalLineDraft(ROLE_ACCOUNTS_RECEIVABLE, net + tax, _ZERO),
            JournalLineDraft(ROLE_SALES, _ZERO, net),
            JournalLineDraft(ROLE_CONSUMPTION_TAX_PAYABLE, _ZERO, tax),
        ],
    )


def _build_purchase_expense(amount: Decimal, tax_rate: Decimal, is_tax_inclusive: bool) -> JournalDraft:
    net, tax = TaxCalculator.calculate_tax(amount, tax_rate, is_tax_inclusive)
    return JournalDraft(
        event_type="purchase_expense",
        description="仕入・経費計上",
        lines=[
            JournalLineDraft(ROLE_EXPENSE, net, _ZERO),
            JournalLineDraft(ROLE_CONSUMPTION_TAX_RECEIVABLE, tax, _ZERO),
            JournalLineDraft(ROLE_ACCOUNTS_PAYABLE, _ZERO, net + tax),
        ],
    )


def _build_payment(amount: Decimal, tax_rate: Decimal, is_tax_inclusive: bool) -> JournalDraft:
    return JournalDraft(
        event_type="payment",
        description="買掛金支払",
        lines=[
            JournalLineDraft(ROLE_ACCOUNTS_PAYABLE, amount, _ZERO),
            JournalLineDraft(ROLE_BANK_DEPOSIT, _ZERO, amount),
        ],
    )


def _build_collection(amount: Decimal, tax_rate: Decimal, is_tax_inclusive: bool) -> JournalDraft:
    return JournalDraft(
        event_type="collection",
        description="売掛金回収",
        lines=[
            JournalLineDraft(ROLE_BANK_DEPOSIT, amount, _ZERO),
            JournalLineDraft(ROLE_ACCOUNTS_RECEIVABLE, _ZERO, amount),
        ],
    )


def _build_depreciation(amount: Decimal, tax_rate: Decimal, is_tax_inclusive: bool) -> JournalDraft:
    return JournalDraft(
        event_type="depreciation",
        description="減価償却費計上",
        lines=[
            JournalLineDraft(ROLE_DEPRECIATION_EXPENSE, amount, _ZERO),
            JournalLineDraft(ROLE_ACCUMULATED_DEPRECIATION, _ZERO, amount),
        ],
    )


# 業務イベント → 仕訳ビルダーの対応表。
_BUILDERS: dict[str, Callable[[Decimal, Decimal, bool], JournalDraft]] = {
    "sales": _build_sales,
    "purchase_expense": _build_purchase_expense,
    "payment": _build_payment,
    "collection": _build_collection,
    "depreciation": _build_depreciation,
}

# 消費税の按分を行うイベント（それ以外は税区分対象外）。
_TAXABLE_EVENTS = frozenset({"sales", "purchase_expense"})


class EventJournalService:
    """業務イベントを貸借一致の仕訳ドラフトへ変換する純粋サービス。"""

    @staticmethod
    def supported_events() -> list[str]:
        return sorted(_BUILDERS.keys())

    @staticmethod
    def build_journal_draft(
        *,
        event_type: str,
        amount: Decimal,
        tax_rate: Decimal = Decimal("0.10"),
        is_tax_inclusive: bool = True,
    ) -> JournalDraft:
        if amount <= _ZERO:
            raise ValueError("amount must be positive")
        builder = _BUILDERS.get(event_type)
        if builder is None:
            raise ValueError(f"unsupported event_type: {event_type}")
        effective_rate = tax_rate if event_type in _TAXABLE_EVENTS else _ZERO
        draft = builder(amount, effective_rate, is_tax_inclusive)
        if draft.total_debit != draft.total_credit:
            raise ValueError("generated journal draft is unbalanced")
        return draft
