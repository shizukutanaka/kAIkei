"""入金明細と請求(売掛金)の自動消込。

支払側(`payment_matching`)と違い、入金は自社が金額を決められないので実務では必ずズレる。

    1. 振込人名が請求先名と一致しない(屋号・カナ略称・代表者名で振り込まれる)
    2. 振込手数料を差し引いて振り込まれる(数百円足りない)
    3. 複数の請求をまとめて1本で振り込まれる / 1つの請求が分割入金される
    4. 多く振り込まれる(次回充当=前受金)

このどれも「金額完全一致」では消し込めず、担当者が請求書の束と睨めっこする工程が残っていた。
本サービスは請求ごとの**残高**を持ち、確実な順に充当する。

    exact(残高完全一致) → aggregate(部分和で複数請求) → fee_adjusted(手数料の許容差)
    → partial(期日の古い請求から順にFIFO充当。残高は残す)
    → 余りは前受金(advance)として区別する

前受金と一部入金を潰して「消込済み」にしないことが要点で、残高と前受金は別々に返す。
振込人名の突合は既存 `bank_reconciliation` の正規化・類似度をそのまま再利用する
(法人格トークン除去・記号除去済みの比較)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.bank_reconciliation import name_similarity

STATUS_SETTLED = "settled"
STATUS_PARTIAL = "partial"
STATUS_ADVANCE = "advance"
STATUS_UNMATCHED = "unmatched"

APPLY_EXACT = "exact"
APPLY_AGGREGATE = "aggregate"
APPLY_FEE_ADJUSTED = "fee_adjusted"
APPLY_PARTIAL = "partial"

DEFAULT_NAME_THRESHOLD = 0.6
MAX_SUBSET_CANDIDATES = 24

_ZERO = Decimal("0")


@dataclass(frozen=True)
class OpenInvoice:
    invoice_id: str
    customer_name: str
    amount: Decimal
    due_date: date


@dataclass(frozen=True)
class Deposit:
    deposit_id: str
    transaction_date: date
    amount: Decimal
    remitter_name: str = ""


@dataclass(frozen=True)
class Allocation:
    invoice_id: str
    applied_amount: Decimal
    fee_absorbed: Decimal
    apply_type: str


@dataclass(frozen=True)
class DepositResult:
    deposit_id: str
    amount: Decimal
    status: str
    allocations: list[Allocation]
    applied_amount: Decimal
    advance_amount: Decimal


@dataclass(frozen=True)
class InvoiceBalance:
    invoice_id: str
    amount: Decimal
    applied_amount: Decimal
    outstanding: Decimal
    settled: bool


@dataclass(frozen=True)
class ReceivableMatchResult:
    deposits: list[DepositResult]
    invoices: list[InvoiceBalance]
    total_applied: Decimal
    total_advance: Decimal
    total_unmatched: Decimal
    total_outstanding: Decimal
    settled_invoice_ids: list[str]
    unmatched_deposit_ids: list[str]


class ReceivableMatchingService:
    """入金と請求を突合し、請求残高・前受金を確定する純粋サービス。"""

    @staticmethod
    def _find_subset(target: Decimal, amounts: list[tuple[str, Decimal]]) -> list[str] | None:
        if len(amounts) > MAX_SUBSET_CANDIDATES:
            return None
        reachable: dict[Decimal, list[str]] = {_ZERO: []}
        for invoice_id, amount in amounts:
            updated = dict(reachable)
            for total, ids in reachable.items():
                new_total = total + amount
                if new_total > target or new_total in updated:
                    continue
                updated[new_total] = [*ids, invoice_id]
            reachable = updated
        found = reachable.get(target)
        if found is None or len(found) < 2:
            return None
        return found

    @classmethod
    def match(
        cls,
        *,
        deposits: list[Deposit],
        invoices: list[OpenInvoice],
        fee_tolerance: Decimal = _ZERO,
        name_threshold: float = DEFAULT_NAME_THRESHOLD,
    ) -> ReceivableMatchResult:
        if fee_tolerance < _ZERO:
            raise ValueError("fee_tolerance must not be negative")
        if not 0.0 <= name_threshold <= 1.0:
            raise ValueError("name_threshold must be between 0 and 1")
        if any(item.amount <= _ZERO for item in deposits):
            raise ValueError("deposit amount must be positive")
        if any(item.amount <= _ZERO for item in invoices):
            raise ValueError("invoice amount must be positive")
        deposit_ids = [item.deposit_id for item in deposits]
        if len(set(deposit_ids)) != len(deposit_ids):
            raise ValueError("deposit_id must be unique")
        invoice_ids = [item.invoice_id for item in invoices]
        if len(set(invoice_ids)) != len(invoice_ids):
            raise ValueError("invoice_id must be unique")

        outstanding: dict[str, Decimal] = {
            invoice.invoice_id: invoice.amount for invoice in invoices
        }
        applied: dict[str, Decimal] = {invoice.invoice_id: _ZERO for invoice in invoices}
        by_id = {invoice.invoice_id: invoice for invoice in invoices}

        deposit_results: list[DepositResult] = []

        for deposit in deposits:
            candidates = [
                invoice
                for invoice in invoices
                if outstanding[invoice.invoice_id] > _ZERO
                and name_similarity(deposit.remitter_name, invoice.customer_name)
                >= name_threshold
            ]
            candidates.sort(key=lambda invoice: (invoice.due_date, invoice.invoice_id))

            allocations: list[Allocation] = []
            remaining = deposit.amount

            exact = [
                invoice
                for invoice in candidates
                if outstanding[invoice.invoice_id] == deposit.amount
            ]
            subset = (
                None
                if exact
                else cls._find_subset(
                    deposit.amount,
                    [
                        (invoice.invoice_id, outstanding[invoice.invoice_id])
                        for invoice in candidates
                    ],
                )
            )
            near = [
                invoice
                for invoice in candidates
                if fee_tolerance > _ZERO
                and _ZERO
                < outstanding[invoice.invoice_id] - deposit.amount
                <= fee_tolerance
            ]

            if len(exact) >= 1:
                invoice = exact[0]
                allocations.append(
                    Allocation(
                        invoice_id=invoice.invoice_id,
                        applied_amount=deposit.amount,
                        fee_absorbed=_ZERO,
                        apply_type=APPLY_EXACT,
                    ),
                )
                remaining = _ZERO
            elif subset is not None:
                for invoice_id in subset:
                    allocations.append(
                        Allocation(
                            invoice_id=invoice_id,
                            applied_amount=outstanding[invoice_id],
                            fee_absorbed=_ZERO,
                            apply_type=APPLY_AGGREGATE,
                        ),
                    )
                remaining = _ZERO
            elif len(near) == 1:
                invoice = near[0]
                fee = outstanding[invoice.invoice_id] - deposit.amount
                allocations.append(
                    Allocation(
                        invoice_id=invoice.invoice_id,
                        applied_amount=deposit.amount,
                        fee_absorbed=fee,
                        apply_type=APPLY_FEE_ADJUSTED,
                    ),
                )
                remaining = _ZERO
            else:
                for invoice in candidates:
                    if remaining <= _ZERO:
                        break
                    balance = outstanding[invoice.invoice_id]
                    applied_amount = min(balance, remaining)
                    allocations.append(
                        Allocation(
                            invoice_id=invoice.invoice_id,
                            applied_amount=applied_amount,
                            fee_absorbed=_ZERO,
                            apply_type=APPLY_PARTIAL,
                        ),
                    )
                    remaining -= applied_amount

            for allocation in allocations:
                outstanding[allocation.invoice_id] -= (
                    allocation.applied_amount + allocation.fee_absorbed
                )
                applied[allocation.invoice_id] += allocation.applied_amount

            applied_total = sum(
                (allocation.applied_amount for allocation in allocations), _ZERO
            )
            if not allocations:
                # 相手先を特定できない入金は前受金ではなく「不明入金」。
                # 前受金に混ぜると次回請求へ勝手に充当されるため区別する。
                status = STATUS_UNMATCHED
                remaining = _ZERO
            elif remaining > _ZERO:
                status = STATUS_ADVANCE
            elif any(
                outstanding[allocation.invoice_id] > _ZERO for allocation in allocations
            ):
                status = STATUS_PARTIAL
            else:
                status = STATUS_SETTLED

            deposit_results.append(
                DepositResult(
                    deposit_id=deposit.deposit_id,
                    amount=deposit.amount,
                    status=status,
                    allocations=allocations,
                    applied_amount=applied_total,
                    advance_amount=remaining,
                ),
            )

        balances = [
            InvoiceBalance(
                invoice_id=invoice.invoice_id,
                amount=invoice.amount,
                applied_amount=applied[invoice.invoice_id],
                outstanding=outstanding[invoice.invoice_id],
                settled=outstanding[invoice.invoice_id] <= _ZERO,
            )
            for invoice in by_id.values()
        ]

        return ReceivableMatchResult(
            deposits=deposit_results,
            invoices=balances,
            total_applied=sum((item.applied_amount for item in deposit_results), _ZERO),
            total_advance=sum((item.advance_amount for item in deposit_results), _ZERO),
            total_unmatched=sum(
                (
                    item.amount
                    for item in deposit_results
                    if item.status == STATUS_UNMATCHED
                ),
                _ZERO,
            ),
            total_outstanding=sum((item.outstanding for item in balances), _ZERO),
            settled_invoice_ids=[item.invoice_id for item in balances if item.settled],
            unmatched_deposit_ids=[
                item.deposit_id
                for item in deposit_results
                if item.status == STATUS_UNMATCHED
            ],
        )
