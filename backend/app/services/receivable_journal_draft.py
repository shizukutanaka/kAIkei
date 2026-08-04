"""入金消込の結果から売掛金の消込仕訳ドラフトを生成する。

消込(`receivable_matching`)で「どの入金がどの請求に充当されたか」まで決まっても、担当者は
それを見ながら1本ずつ仕訳を手で起票していた。充当が決まれば仕訳は一意なので、この工程は消せる。

    (借) 現金預金    入金額          (貸) 売掛金    充当額 + 手数料(取引先別)
    (借) 支払手数料  先方負担手数料   (貸) 前受金    過入金
                                    (貸) 仮受金    相手先不明の入金

要点は3つ。

    1. 手数料を差し引かれた入金でも**売掛金は請求額の全額を落とす**(差額は支払手数料)。
       入金額だけ落とすと売掛金に数百円の残骸が永久に残り、翌期の残高確認で必ず問題になる。
    2. 過入金は売掛金のマイナスにせず**前受金**に振り替える(債権残高を負にしない)。
    3. 相手先不明の入金も**仮受金で必ず起票する**。銀行残高は実際に動いているので、
       仕訳を起こさないと現金預金が合わなくなる。判明後に仮受金→売掛金へ振り替える。

勘定コードは会社ごとに異なるため、既存 `payroll_journal_draft` と同じく勘定ロールで表現し、
実際の勘定科目への対応付けは呼び出し側が行う。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.receivable_matching import (
    STATUS_UNMATCHED,
    ReceivableMatchResult,
)

ROLE_BANK_DEPOSIT = "bank_deposit"
ROLE_ACCOUNTS_RECEIVABLE = "accounts_receivable"
ROLE_TRANSFER_FEE_EXPENSE = "transfer_fee_expense"
ROLE_ADVANCE_RECEIVED = "advance_received"
ROLE_SUSPENSE_RECEIPT = "suspense_receipt"

DRAFT_RECEIVABLE_SETTLEMENT = "receivable_settlement"
DRAFT_SUSPENSE_RECEIPT = "suspense_receipt"

_ZERO = Decimal("0")


@dataclass(frozen=True)
class ReceivableDraftLine:
    account_role: str
    debit: Decimal
    credit: Decimal
    invoice_id: str | None = None
    partner_name: str = ""


@dataclass(frozen=True)
class ReceivableJournalDraft:
    draft_type: str
    deposit_id: str
    description: str
    transaction_date: date
    lines: list[ReceivableDraftLine]
    total_debit: Decimal
    total_credit: Decimal


@dataclass(frozen=True)
class ReceivableJournalResult:
    drafts: list[ReceivableJournalDraft]
    total_receivable_cleared: Decimal
    total_fee_expense: Decimal
    total_advance_received: Decimal
    total_suspense: Decimal
    balanced: bool


class ReceivableJournalDraftService:
    """消込結果から売掛金の消込仕訳ドラフトを組み立てる純粋サービス。"""

    @staticmethod
    def _build(
        draft_type: str,
        deposit_id: str,
        description: str,
        transaction_date: date,
        lines: list[ReceivableDraftLine],
    ) -> ReceivableJournalDraft:
        kept = [line for line in lines if line.debit > _ZERO or line.credit > _ZERO]
        total_debit = sum((line.debit for line in kept), _ZERO)
        total_credit = sum((line.credit for line in kept), _ZERO)
        if total_debit != total_credit:
            raise ValueError(f"generated {draft_type} draft is unbalanced ({deposit_id})")
        return ReceivableJournalDraft(
            draft_type=draft_type,
            deposit_id=deposit_id,
            description=description,
            transaction_date=transaction_date,
            lines=kept,
            total_debit=total_debit,
            total_credit=total_credit,
        )

    @classmethod
    def generate(
        cls,
        result: ReceivableMatchResult,
        *,
        transaction_dates: dict[str, date],
        partner_names: dict[str, str] | None = None,
    ) -> ReceivableJournalResult:
        names = partner_names or {}
        drafts: list[ReceivableJournalDraft] = []

        for deposit in result.deposits:
            transaction_date = transaction_dates.get(deposit.deposit_id)
            if transaction_date is None:
                raise ValueError(f"transaction_date is missing for deposit {deposit.deposit_id}")

            if deposit.status == STATUS_UNMATCHED:
                drafts.append(
                    cls._build(
                        DRAFT_SUSPENSE_RECEIPT,
                        deposit.deposit_id,
                        f"入金(相手先不明) {deposit.deposit_id}",
                        transaction_date,
                        [
                            ReceivableDraftLine(ROLE_BANK_DEPOSIT, deposit.amount, _ZERO),
                            ReceivableDraftLine(ROLE_SUSPENSE_RECEIPT, _ZERO, deposit.amount),
                        ],
                    ),
                )
                continue

            fee_total = sum((a.fee_absorbed for a in deposit.allocations), _ZERO)
            lines: list[ReceivableDraftLine] = [
                ReceivableDraftLine(ROLE_BANK_DEPOSIT, deposit.amount, _ZERO),
                ReceivableDraftLine(ROLE_TRANSFER_FEE_EXPENSE, fee_total, _ZERO),
            ]
            for allocation in deposit.allocations:
                lines.append(
                    ReceivableDraftLine(
                        ROLE_ACCOUNTS_RECEIVABLE,
                        _ZERO,
                        allocation.applied_amount + allocation.fee_absorbed,
                        invoice_id=allocation.invoice_id,
                        partner_name=names.get(allocation.invoice_id, ""),
                    ),
                )
            lines.append(
                ReceivableDraftLine(ROLE_ADVANCE_RECEIVED, _ZERO, deposit.advance_amount),
            )
            drafts.append(
                cls._build(
                    DRAFT_RECEIVABLE_SETTLEMENT,
                    deposit.deposit_id,
                    f"売掛金入金消込 {deposit.deposit_id}",
                    transaction_date,
                    lines,
                ),
            )

        def _sum(role: str, *, debit: bool) -> Decimal:
            return sum(
                (
                    (line.debit if debit else line.credit)
                    for draft in drafts
                    for line in draft.lines
                    if line.account_role == role
                ),
                _ZERO,
            )

        return ReceivableJournalResult(
            drafts=drafts,
            total_receivable_cleared=_sum(ROLE_ACCOUNTS_RECEIVABLE, debit=False),
            total_fee_expense=_sum(ROLE_TRANSFER_FEE_EXPENSE, debit=True),
            total_advance_received=_sum(ROLE_ADVANCE_RECEIVED, debit=False),
            total_suspense=_sum(ROLE_SUSPENSE_RECEIPT, debit=False),
            balanced=all(draft.total_debit == draft.total_credit for draft in drafts),
        )
