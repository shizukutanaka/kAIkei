"""振込データと銀行出金明細の突合(支払消込)。

既存の `bank_reconciliation` は銀行明細と仕訳明細を**1対1**で突合する。しかし総合振込を使うと
銀行側には明細ごとではなく「1本の合算出金」が立つため、1対1の消込ではこの出金が永久に残り、
担当者が電卓で内訳を足し合わせて照合する工程が残る。ここを削除する。

    銀行出金 349,340 = 山田商事 100,000 + 鈴木工業 249,340   ← 1対Nの突合が要る

さらに振込手数料の扱いで金額が一致しない:

    当方負担 → 支払額とは別に手数料の出金が立つ、または出金額 = 支払額 + 手数料
    先方負担 → 出金額 = 支払額 − 手数料

そこで突合を3段階に分け、確実なものから順に確定させる(先に曖昧な突合を確定させると、
本来一致するはずの明細が食われて未消込が増える)。

    1. exact     … 金額完全一致の1対1
    2. aggregate … 複数支払の合計と一致する1対N(部分和をDPで探索)
    3. fee_adjusted … 手数料の許容差以内で一致する1対1

支払は1件につき1回しか使わず、どの段階でも一致しなかったものは `unmatched_*` として返す。
自動で消し込めなかったものを黙って捨てず「人が見るべき残り」として明示するのが目的。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

MATCH_EXACT = "exact"
MATCH_AGGREGATE = "aggregate"
MATCH_FEE_ADJUSTED = "fee_adjusted"

DEFAULT_DATE_TOLERANCE_DAYS = 3
# 部分和探索の打ち切り。組合せが爆発する日は自動突合せず人手に回す。
MAX_SUBSET_CANDIDATES = 24
MAX_SUBSET_STATES = 200000

_ZERO = Decimal("0")


@dataclass(frozen=True)
class ExpectedPayment:
    payment_id: str
    payee_name: str
    amount: Decimal
    payment_date: date


@dataclass(frozen=True)
class BankWithdrawal:
    line_id: str
    transaction_date: date
    amount: Decimal
    description: str = ""


@dataclass(frozen=True)
class PaymentMatch:
    line_id: str
    payment_ids: list[str]
    withdrawal_amount: Decimal
    matched_amount: Decimal
    difference: Decimal
    match_type: str


@dataclass(frozen=True)
class PaymentMatchResult:
    matches: list[PaymentMatch]
    unmatched_line_ids: list[str]
    unmatched_payment_ids: list[str]
    matched_count: int
    matched_amount_total: Decimal
    unmatched_withdrawal_total: Decimal
    unmatched_payment_total: Decimal
    fully_reconciled: bool


class PaymentMatchingService:
    """振込データと銀行出金明細を突合する純粋サービス。"""

    @staticmethod
    def _within_date(withdrawal: BankWithdrawal, payment: ExpectedPayment, tolerance: int) -> bool:
        return abs((withdrawal.transaction_date - payment.payment_date).days) <= tolerance

    @classmethod
    def _find_subset(
        cls,
        target: Decimal,
        payments: list[ExpectedPayment],
    ) -> list[str] | None:
        """合計が target と一致する支払の組合せを返す(2件以上)。無ければ None。"""
        if len(payments) > MAX_SUBSET_CANDIDATES:
            return None
        reachable: dict[Decimal, list[str]] = {_ZERO: []}
        for payment in payments:
            updated = dict(reachable)
            for total, ids in reachable.items():
                new_total = total + payment.amount
                if new_total > target or new_total in updated:
                    continue
                updated[new_total] = [*ids, payment.payment_id]
                if len(updated) > MAX_SUBSET_STATES:
                    return None
            reachable = updated
        found = reachable.get(target)
        if found is None or len(found) < 2:
            return None
        return found

    @classmethod
    def match(
        cls,
        *,
        withdrawals: list[BankWithdrawal],
        payments: list[ExpectedPayment],
        date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
        fee_tolerance: Decimal = _ZERO,
    ) -> PaymentMatchResult:
        if date_tolerance_days < 0:
            raise ValueError("date_tolerance_days must not be negative")
        if fee_tolerance < _ZERO:
            raise ValueError("fee_tolerance must not be negative")
        if any(item.amount <= _ZERO for item in withdrawals):
            raise ValueError("withdrawal amount must be positive")
        if any(item.amount <= _ZERO for item in payments):
            raise ValueError("payment amount must be positive")
        payment_ids = [payment.payment_id for payment in payments]
        if len(set(payment_ids)) != len(payment_ids):
            raise ValueError("payment_id must be unique")
        line_ids = [withdrawal.line_id for withdrawal in withdrawals]
        if len(set(line_ids)) != len(line_ids):
            raise ValueError("line_id must be unique")

        remaining_payments = {payment.payment_id: payment for payment in payments}
        remaining_withdrawals = list(withdrawals)
        matches: list[PaymentMatch] = []

        def candidates(withdrawal: BankWithdrawal) -> list[ExpectedPayment]:
            return [
                payment
                for payment in remaining_payments.values()
                if cls._within_date(withdrawal, payment, date_tolerance_days)
            ]

        def commit(
            withdrawal: BankWithdrawal,
            ids: list[str],
            match_type: str,
        ) -> None:
            matched_amount = sum(
                (remaining_payments[pid].amount for pid in ids), _ZERO
            )
            matches.append(
                PaymentMatch(
                    line_id=withdrawal.line_id,
                    payment_ids=ids,
                    withdrawal_amount=withdrawal.amount,
                    matched_amount=matched_amount,
                    difference=withdrawal.amount - matched_amount,
                    match_type=match_type,
                ),
            )
            for pid in ids:
                del remaining_payments[pid]

        # 1) 金額完全一致の1対1。
        for withdrawal in list(remaining_withdrawals):
            exact = [
                payment
                for payment in candidates(withdrawal)
                if payment.amount == withdrawal.amount
            ]
            if len(exact) != 1:
                continue
            commit(withdrawal, [exact[0].payment_id], MATCH_EXACT)
            remaining_withdrawals.remove(withdrawal)

        # 2) 合算出金(1対N)。
        for withdrawal in list(remaining_withdrawals):
            subset = cls._find_subset(withdrawal.amount, candidates(withdrawal))
            if subset is None:
                continue
            commit(withdrawal, subset, MATCH_AGGREGATE)
            remaining_withdrawals.remove(withdrawal)

        # 3) 手数料の許容差以内の1対1。
        if fee_tolerance > _ZERO:
            for withdrawal in list(remaining_withdrawals):
                near = [
                    payment
                    for payment in candidates(withdrawal)
                    if abs(withdrawal.amount - payment.amount) <= fee_tolerance
                ]
                if len(near) != 1:
                    continue
                commit(withdrawal, [near[0].payment_id], MATCH_FEE_ADJUSTED)
                remaining_withdrawals.remove(withdrawal)

        matched_total = sum((match.withdrawal_amount for match in matches), _ZERO)
        return PaymentMatchResult(
            matches=matches,
            unmatched_line_ids=[item.line_id for item in remaining_withdrawals],
            unmatched_payment_ids=[
                payment.payment_id
                for payment in payments
                if payment.payment_id in remaining_payments
            ],
            matched_count=len(matches),
            matched_amount_total=matched_total,
            unmatched_withdrawal_total=sum(
                (item.amount for item in remaining_withdrawals), _ZERO
            ),
            unmatched_payment_total=sum(
                (payment.amount for payment in remaining_payments.values()), _ZERO
            ),
            fully_reconciled=not remaining_withdrawals and not remaining_payments,
        )
