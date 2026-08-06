"""貸倒判定の結果から貸倒仕訳ドラフトと消費税39条の控除税額を生成する。

貸倒判定(#88)で「どの債権をいくら落とし、当期の繰入限度額がいくらか」まで決まっても、
担当者は引当金の取崩額を電卓で出し、貸倒損失と仮受消費税に割り振って手で起票していた。
判定結果と経理方式が分かれば仕訳は一意なので、この工程を削除する。

貸倒れの仕訳(税抜経理):

    (借) 貸倒引当金      取崩額        (貸) 売掛金   貸倒れ税込額
    (借) 貸倒損失        残額(税抜相当)
    (借) 仮受消費税等    39条の控除税額

要点は4つ。

    1. **引当金を先に取り崩す**。前期末に引き当てた債権が実際に貸倒れたのに全額を貸倒損失に
       すると、引当金が残ったまま費用が二重に立つ。期首残高を上限に古い債権から充当する。
    2. **税込額から消費税を抜く**(消費税法39条)。貸倒れとなった税込金額に含まれる消費税額は
       売上税額から控除できる。税抜経理では仮受消費税等の借方に立て、貸倒損失は税抜相当額。
       **税込経理では仕訳を分けない**(貸倒損失が税込)が、申告上の控除税額は同額なので
       `total_consumption_tax_deduction` として必ず返す。
    3. **課税資産の譲渡等に係る債権でなければ控除しない**(貸付金・保証金等)。`tax_rate` に 0 を
       指定した債権は全額が貸倒損失になる。
    4. **期末の引当金を目標残高に合わせる**。差額補充法は不足額だけを繰入れ、洗替法は残高を
       全額戻し入れて限度額を繰り入れる。目標残高は #88 の `total_reserve_limit`。

勘定コードは会社ごとに異なるため、既存の仕訳ドラフト各サービスと同じく勘定ロールで表現する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.services.bad_debt_assessment import (
    TREATMENT_BAD_DEBT_LOSS,
    BadDebtAssessmentResult,
)
from app.services.bad_debt_consumption_tax import BadDebtConsumptionTaxService

ROLE_ACCOUNTS_RECEIVABLE = "accounts_receivable"
ROLE_BAD_DEBT_ALLOWANCE = "bad_debt_allowance"
ROLE_BAD_DEBT_LOSS = "bad_debt_loss"
ROLE_CONSUMPTION_TAX_RECEIVED = "consumption_tax_received"
ROLE_ALLOWANCE_PROVISION = "bad_debt_allowance_provision"
ROLE_ALLOWANCE_REVERSAL = "bad_debt_allowance_reversal"

DRAFT_WRITE_OFF = "bad_debt_write_off"
DRAFT_ALLOWANCE_PROVISION = "allowance_provision"
DRAFT_ALLOWANCE_REVERSAL = "allowance_reversal"

TAX_EXCLUSIVE = "exclusive"
TAX_INCLUSIVE = "inclusive"

METHOD_DIFFERENCE = "difference"
METHOD_REVERSAL = "reversal"

DEFAULT_TAX_RATE = Decimal("0.10")

_ZERO = Decimal("0")


@dataclass(frozen=True)
class BadDebtDraftLine:
    account_role: str
    debit: Decimal
    credit: Decimal
    receivable_id: str | None = None
    partner_name: str = ""


@dataclass(frozen=True)
class BadDebtJournalDraft:
    draft_type: str
    reference_id: str
    description: str
    transaction_date: date
    lines: list[BadDebtDraftLine]
    total_debit: Decimal
    total_credit: Decimal


@dataclass(frozen=True)
class BadDebtJournalResult:
    transaction_date: date
    drafts: list[BadDebtJournalDraft]
    total_write_off: Decimal
    total_allowance_used: Decimal
    total_loss_expense: Decimal
    total_consumption_tax_deduction: Decimal
    allowance_opening_balance: Decimal
    allowance_after_write_off: Decimal
    allowance_target: Decimal
    provision_amount: Decimal
    reversal_amount: Decimal
    allowance_closing_balance: Decimal
    balanced: bool


class BadDebtJournalDraftService:
    """貸倒判定の結果から貸倒仕訳ドラフトを組み立てる純粋サービス。"""

    @staticmethod
    def _build(
        *,
        draft_type: str,
        reference_id: str,
        description: str,
        transaction_date: date,
        lines: list[BadDebtDraftLine],
    ) -> BadDebtJournalDraft:
        kept = [line for line in lines if line.debit > _ZERO or line.credit > _ZERO]
        total_debit = sum((line.debit for line in kept), _ZERO)
        total_credit = sum((line.credit for line in kept), _ZERO)
        if total_debit != total_credit:
            raise ValueError(f"generated {draft_type} draft is unbalanced ({reference_id})")
        return BadDebtJournalDraft(
            draft_type=draft_type,
            reference_id=reference_id,
            description=description,
            transaction_date=transaction_date,
            lines=kept,
            total_debit=total_debit,
            total_credit=total_credit,
        )

    @classmethod
    def generate(
        cls,
        assessment: BadDebtAssessmentResult,
        *,
        transaction_date: date,
        allowance_balance: Decimal = _ZERO,
        tax_rates: dict[str, Decimal] | None = None,
        tax_treatment: str = TAX_EXCLUSIVE,
        allowance_method: str = METHOD_DIFFERENCE,
    ) -> BadDebtJournalResult:
        if allowance_balance < _ZERO:
            raise ValueError("allowance_balance must not be negative")
        if tax_treatment not in (TAX_EXCLUSIVE, TAX_INCLUSIVE):
            raise ValueError(f"無効な経理方式: {tax_treatment}")
        if allowance_method not in (METHOD_DIFFERENCE, METHOD_REVERSAL):
            raise ValueError(f"無効な引当金の計上方法: {allowance_method}")

        rates = dict(tax_rates or {})
        known_ids = {item.receivable_id for item in assessment.items}
        unknown = sorted(set(rates) - known_ids)
        if unknown:
            raise ValueError(f"判定結果に存在しない債権の税率が指定されている: {unknown[0]}")

        drafts: list[BadDebtJournalDraft] = []
        remaining_allowance = allowance_balance
        total_write_off = _ZERO
        total_allowance_used = _ZERO
        total_loss_expense = _ZERO
        total_tax_deduction = _ZERO

        for item in assessment.items:
            if item.treatment != TREATMENT_BAD_DEBT_LOSS or item.loss_amount <= _ZERO:
                continue

            rate = rates.get(item.receivable_id, DEFAULT_TAX_RATE)
            if rate < _ZERO:
                raise ValueError("tax_rate must not be negative")
            deductible_tax = _ZERO
            if rate > _ZERO:
                deductible_tax = BadDebtConsumptionTaxService.compute(
                    bad_debt_amount=item.loss_amount,
                    tax_rate=rate,
                ).deductible_tax
            total_tax_deduction += deductible_tax

            allowance_used = min(remaining_allowance, item.loss_amount)
            remaining_allowance -= allowance_used
            total_allowance_used += allowance_used

            tax_line = deductible_tax if tax_treatment == TAX_EXCLUSIVE else _ZERO
            loss_expense = item.loss_amount - allowance_used - tax_line
            if loss_expense < _ZERO:
                # 引当金が貸倒額を超える場合でも消費税分は必ず立てるため、取崩額を減らす
                allowance_used += loss_expense
                remaining_allowance -= loss_expense
                total_allowance_used += loss_expense
                loss_expense = _ZERO
            total_loss_expense += loss_expense
            total_write_off += item.loss_amount

            drafts.append(
                cls._build(
                    draft_type=DRAFT_WRITE_OFF,
                    reference_id=item.receivable_id,
                    description=f"貸倒れ({item.basis}) {item.customer_name}",
                    transaction_date=transaction_date,
                    lines=[
                        BadDebtDraftLine(
                            ROLE_BAD_DEBT_ALLOWANCE,
                            allowance_used,
                            _ZERO,
                            receivable_id=item.receivable_id,
                            partner_name=item.customer_name,
                        ),
                        BadDebtDraftLine(
                            ROLE_BAD_DEBT_LOSS,
                            loss_expense,
                            _ZERO,
                            receivable_id=item.receivable_id,
                            partner_name=item.customer_name,
                        ),
                        BadDebtDraftLine(ROLE_CONSUMPTION_TAX_RECEIVED, tax_line, _ZERO),
                        BadDebtDraftLine(
                            ROLE_ACCOUNTS_RECEIVABLE,
                            _ZERO,
                            item.loss_amount,
                            receivable_id=item.receivable_id,
                            partner_name=item.customer_name,
                        ),
                    ],
                ),
            )

        target = assessment.total_reserve_limit
        if allowance_method == METHOD_REVERSAL:
            reversal = remaining_allowance
            provision = target
        else:
            difference = target - remaining_allowance
            provision = max(difference, _ZERO)
            reversal = max(-difference, _ZERO)

        if reversal > _ZERO:
            drafts.append(
                cls._build(
                    draft_type=DRAFT_ALLOWANCE_REVERSAL,
                    reference_id="allowance",
                    description="貸倒引当金戻入",
                    transaction_date=transaction_date,
                    lines=[
                        BadDebtDraftLine(ROLE_BAD_DEBT_ALLOWANCE, reversal, _ZERO),
                        BadDebtDraftLine(ROLE_ALLOWANCE_REVERSAL, _ZERO, reversal),
                    ],
                ),
            )
        if provision > _ZERO:
            drafts.append(
                cls._build(
                    draft_type=DRAFT_ALLOWANCE_PROVISION,
                    reference_id="allowance",
                    description="貸倒引当金繰入",
                    transaction_date=transaction_date,
                    lines=[
                        BadDebtDraftLine(ROLE_ALLOWANCE_PROVISION, provision, _ZERO),
                        BadDebtDraftLine(ROLE_BAD_DEBT_ALLOWANCE, _ZERO, provision),
                    ],
                ),
            )

        return BadDebtJournalResult(
            transaction_date=transaction_date,
            drafts=drafts,
            total_write_off=total_write_off,
            total_allowance_used=total_allowance_used,
            total_loss_expense=total_loss_expense,
            total_consumption_tax_deduction=total_tax_deduction,
            allowance_opening_balance=allowance_balance,
            allowance_after_write_off=remaining_allowance,
            allowance_target=target,
            provision_amount=provision,
            reversal_amount=reversal,
            allowance_closing_balance=remaining_allowance - reversal + provision,
            balanced=all(draft.total_debit == draft.total_credit for draft in drafts),
        )
