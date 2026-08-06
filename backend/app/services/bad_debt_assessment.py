"""滞留債権の貸倒判定(貸倒損失・個別評価・一括評価への自動振分け)。

エイジング(#87)が滞留債権を洗い出しても、「どれを貸倒損失で落とし、どれを個別評価の
引当にし、残りを一括評価(#66)に回すか」は担当者が債権ごとに通達を引きながら判断していた。
事由と日付と担保額が分かれば税務上の扱いは一意に決まるので、その判断を機械化する。

貸倒損失(法人税基本通達):
    9-6-1 法律上の貸倒れ  : 更生計画/再生計画の認可決定・特別清算協定の認可で切り捨てられた
                            金額、書面による債務免除額 → 切捨額を損金
    9-6-2 事実上の貸倒れ  : 資産状況・支払能力からみて全額回収不能 → 全額を損金。
                            **担保物があるときはその処分後**でなければ計上できない
    9-6-3 形式上の貸倒れ  : 継続的取引の停止から1年以上経過した売掛債権 →
                            **備忘価額1円を残して**損金(1円を残さないと要件を満たさない)

個別評価金銭債権の繰入限度額(法人税法52条1項・施行令96条1項):
    1号 長期棚上げ: 弁済猶予・賦払 → 事由発生後5年以内に弁済される額と担保額を除いた金額
    2号 債務超過等: 債務超過が相当期間継続 → 取立不能見込額(担保・保証による回収額を除く)
    3号 形式基準  : 更生/再生/破産/特別清算の申立て、手形交換所の取引停止処分 →
                    (債権額 − 担保額 − 実質的に債権とみられない金額) × 50%

上記いずれにも当たらない債権だけが一括評価金銭債権となり、そのまま #66 の入力になる
(同じ債権を個別評価と一括評価で二重に引き当てることはできない)。

判定できない組み合わせ(担保付きで全額回収不能等)は機械的に落とさず `requires_manual` に
回す。貸倒れは損金算入額が大きく、否認されると修正申告になるため、迷ったら人に返す。
基準日は呼び出し側が渡す(サーバ時刻に依存すると同じ入力でも結果が変わる)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.services.bad_debt_reserve import BadDebtReserveResult, BadDebtReserveService

EVENT_NONE = "none"
# 法律上の切捨て → 貸倒損失(9-6-1)
EVENT_REORGANIZATION_PLAN = "reorganization_plan"
EVENT_REHABILITATION_PLAN = "rehabilitation_plan"
EVENT_SPECIAL_LIQUIDATION_AGREEMENT = "special_liquidation_agreement"
EVENT_DEBT_FORGIVENESS = "debt_forgiveness"
# 形式基準 → 個別評価(令96条1項3号・50%)
EVENT_REORGANIZATION_FILING = "reorganization_filing"
EVENT_REHABILITATION_FILING = "rehabilitation_filing"
EVENT_BANKRUPTCY_FILING = "bankruptcy_filing"
EVENT_SPECIAL_LIQUIDATION_FILING = "special_liquidation_filing"
EVENT_BILL_SUSPENSION = "bill_suspension"
# 債務超過等 → 個別評価(令96条1項2号)
EVENT_INSOLVENCY = "insolvency"
# 弁済猶予・賦払 → 個別評価(令96条1項1号)
EVENT_DEFERRED_PAYMENT = "deferred_payment"

_WRITE_OFF_EVENTS = frozenset(
    {
        EVENT_REORGANIZATION_PLAN,
        EVENT_REHABILITATION_PLAN,
        EVENT_SPECIAL_LIQUIDATION_AGREEMENT,
        EVENT_DEBT_FORGIVENESS,
    },
)
_FORMAL_EVENTS = frozenset(
    {
        EVENT_REORGANIZATION_FILING,
        EVENT_REHABILITATION_FILING,
        EVENT_BANKRUPTCY_FILING,
        EVENT_SPECIAL_LIQUIDATION_FILING,
        EVENT_BILL_SUSPENSION,
    },
)
_KNOWN_EVENTS = (
    _WRITE_OFF_EVENTS
    | _FORMAL_EVENTS
    | {EVENT_NONE, EVENT_INSOLVENCY, EVENT_DEFERRED_PAYMENT}
)

TREATMENT_BAD_DEBT_LOSS = "bad_debt_loss"
TREATMENT_INDIVIDUAL_RESERVE = "individual_reserve"
TREATMENT_GENERAL_RESERVE = "general_reserve"
TREATMENT_MANUAL = "requires_manual"

BASIS_LEGAL_WRITE_OFF = "9-6-1"
BASIS_FACTUAL_LOSS = "9-6-2"
BASIS_TRADE_RECEIVABLE_LOSS = "9-6-3"
BASIS_LONG_TERM_DEFERRAL = "令96条1項1号"
BASIS_INSOLVENCY = "令96条1項2号"
BASIS_FORMAL = "令96条1項3号"
BASIS_GENERAL = "一括評価"

# 9-6-3 の備忘価額。1円を残さないと形式上の貸倒れの要件を満たさない。
MEMORANDUM_VALUE = Decimal("1")
# 継続的取引の停止から貸倒れを認められるまでの期間(9-6-3)。
TRADE_SUSPENSION_DAYS = 365
FORMAL_RESERVE_RATE = Decimal("0.5")

_ZERO = Decimal("0")


@dataclass(frozen=True)
class DebtorReceivable:
    receivable_id: str
    customer_code: str
    customer_name: str
    amount: Decimal
    due_date: date
    event: str = EVENT_NONE
    event_date: date | None = None
    secured_amount: Decimal = _ZERO
    offsettable_amount: Decimal = _ZERO
    written_off_amount: Decimal = _ZERO
    repayment_within_5years: Decimal = _ZERO
    unrecoverable: bool = False
    is_trade_receivable: bool = True
    last_transaction_date: date | None = None


@dataclass(frozen=True)
class AssessedReceivable:
    receivable_id: str
    customer_code: str
    customer_name: str
    amount: Decimal
    treatment: str
    basis: str
    loss_amount: Decimal
    reserve_limit: Decimal
    general_base_amount: Decimal
    note: str


@dataclass(frozen=True)
class BadDebtAssessmentResult:
    as_of: date
    items: list[AssessedReceivable] = field(default_factory=list)
    total_loss: Decimal = _ZERO
    total_individual_reserve: Decimal = _ZERO
    general_receivables: Decimal = _ZERO
    general_offsettable: Decimal = _ZERO
    general_reserve: BadDebtReserveResult | None = None
    total_reserve_limit: Decimal = _ZERO
    manual_receivable_ids: list[str] = field(default_factory=list)


class BadDebtAssessmentService:
    """滞留債権を貸倒損失・個別評価・一括評価に振り分ける純粋サービス。"""

    @staticmethod
    def _validate(receivable: DebtorReceivable) -> None:
        if receivable.event not in _KNOWN_EVENTS:
            raise ValueError(f"無効な貸倒事由: {receivable.event}")
        if receivable.amount <= _ZERO:
            raise ValueError("amount must be positive")
        for name, value in (
            ("secured_amount", receivable.secured_amount),
            ("offsettable_amount", receivable.offsettable_amount),
            ("written_off_amount", receivable.written_off_amount),
            ("repayment_within_5years", receivable.repayment_within_5years),
        ):
            if value < _ZERO:
                raise ValueError(f"{name} must not be negative")
            if value > receivable.amount:
                raise ValueError(f"{name} must not exceed amount")
        if receivable.event in _WRITE_OFF_EVENTS and receivable.written_off_amount <= _ZERO:
            raise ValueError("切捨て・債務免除の事由には written_off_amount が必要")

    @classmethod
    def _assess_one(
        cls,
        *,
        as_of: date,
        receivable: DebtorReceivable,
    ) -> AssessedReceivable:
        cls._validate(receivable)

        def build(
            *,
            treatment: str,
            basis: str,
            loss: Decimal = _ZERO,
            reserve: Decimal = _ZERO,
            general: Decimal = _ZERO,
            note: str = "",
        ) -> AssessedReceivable:
            return AssessedReceivable(
                receivable_id=receivable.receivable_id,
                customer_code=receivable.customer_code,
                customer_name=receivable.customer_name,
                amount=receivable.amount,
                treatment=treatment,
                basis=basis,
                loss_amount=loss,
                reserve_limit=reserve,
                general_base_amount=general,
                note=note,
            )

        if receivable.event in _WRITE_OFF_EVENTS:
            remaining = receivable.amount - receivable.written_off_amount
            if remaining > _ZERO:
                return build(
                    treatment=TREATMENT_MANUAL,
                    basis=BASIS_LEGAL_WRITE_OFF,
                    loss=receivable.written_off_amount,
                    note="切捨額は貸倒損失。残額は弁済条件により個別評価の要否を判断すること",
                )
            return build(
                treatment=TREATMENT_BAD_DEBT_LOSS,
                basis=BASIS_LEGAL_WRITE_OFF,
                loss=receivable.written_off_amount,
                note="法律上の貸倒れ(切捨額の全額を損金)",
            )

        if receivable.unrecoverable:
            if receivable.secured_amount > _ZERO:
                return build(
                    treatment=TREATMENT_MANUAL,
                    basis=BASIS_FACTUAL_LOSS,
                    note="担保物の処分後でなければ事実上の貸倒れを計上できない",
                )
            return build(
                treatment=TREATMENT_BAD_DEBT_LOSS,
                basis=BASIS_FACTUAL_LOSS,
                loss=receivable.amount,
                note="事実上の貸倒れ(全額回収不能・損金経理が要件)",
            )

        if (
            receivable.event == EVENT_NONE
            and receivable.is_trade_receivable
            and receivable.last_transaction_date is not None
            and receivable.secured_amount <= _ZERO
            and (as_of - max(receivable.last_transaction_date, receivable.due_date)).days
            >= TRADE_SUSPENSION_DAYS
        ):
            return build(
                treatment=TREATMENT_BAD_DEBT_LOSS,
                basis=BASIS_TRADE_RECEIVABLE_LOSS,
                loss=receivable.amount - MEMORANDUM_VALUE,
                note="取引停止後1年以上経過(備忘価額1円を残す)",
            )

        if receivable.event == EVENT_DEFERRED_PAYMENT:
            reserve = (
                receivable.amount
                - receivable.repayment_within_5years
                - receivable.secured_amount
            )
            return build(
                treatment=TREATMENT_INDIVIDUAL_RESERVE,
                basis=BASIS_LONG_TERM_DEFERRAL,
                reserve=max(reserve, _ZERO),
                note="長期棚上げ(5年以内の弁済予定額と担保額を控除)",
            )

        if receivable.event == EVENT_INSOLVENCY:
            return build(
                treatment=TREATMENT_INDIVIDUAL_RESERVE,
                basis=BASIS_INSOLVENCY,
                reserve=max(receivable.amount - receivable.secured_amount, _ZERO),
                note="債務超過等による取立不能見込額(担保・保証による回収額を除く)",
            )

        if receivable.event in _FORMAL_EVENTS:
            base = (
                receivable.amount - receivable.secured_amount - receivable.offsettable_amount
            )
            reserve = max(base, _ZERO) * FORMAL_RESERVE_RATE
            return build(
                treatment=TREATMENT_INDIVIDUAL_RESERVE,
                basis=BASIS_FORMAL,
                reserve=reserve.quantize(Decimal("1")),
                note="形式基準(担保額・実質的に債権とみられない金額を控除した額の50%)",
            )

        return build(
            treatment=TREATMENT_GENERAL_RESERVE,
            basis=BASIS_GENERAL,
            general=receivable.amount,
            note="一括評価金銭債権",
        )

    @classmethod
    def assess(
        cls,
        *,
        as_of: date,
        receivables: list[DebtorReceivable],
        industry: str,
        statutory_rate: Decimal | None = None,
    ) -> BadDebtAssessmentResult:
        ids = [receivable.receivable_id for receivable in receivables]
        if len(set(ids)) != len(ids):
            raise ValueError("receivable_id must be unique")

        items = [cls._assess_one(as_of=as_of, receivable=receivable) for receivable in receivables]

        general_offsettable = sum(
            (
                receivable.offsettable_amount
                for receivable, item in zip(receivables, items, strict=True)
                if item.treatment == TREATMENT_GENERAL_RESERVE
            ),
            _ZERO,
        )
        general_receivables = sum((item.general_base_amount for item in items), _ZERO)

        general_reserve: BadDebtReserveResult | None = None
        if general_receivables > _ZERO:
            general_reserve = BadDebtReserveService.compute(
                receivables=general_receivables,
                industry=industry,
                non_receivable_amount=general_offsettable,
                statutory_rate=statutory_rate,
            )

        total_individual_reserve = sum((item.reserve_limit for item in items), _ZERO)
        general_limit = general_reserve.reserve_limit if general_reserve else _ZERO

        return BadDebtAssessmentResult(
            as_of=as_of,
            items=items,
            total_loss=sum((item.loss_amount for item in items), _ZERO),
            total_individual_reserve=total_individual_reserve,
            general_receivables=general_receivables,
            general_offsettable=general_offsettable,
            general_reserve=general_reserve,
            total_reserve_limit=total_individual_reserve + general_limit,
            manual_receivable_ids=[
                item.receivable_id for item in items if item.treatment == TREATMENT_MANUAL
            ],
        )
