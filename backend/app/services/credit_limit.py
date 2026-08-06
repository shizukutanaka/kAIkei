"""取引先ごとの与信限度額チェック(受注可否の判定と与信枠の残高管理)。

貸倒れ(#88/#89)を仕訳まで自動化しても、次の貸倒れを止める工程は残っている。受注を受けるたびに
担当者が「この取引先はいくらまで出荷していいか」を売掛残高・受注残・滞留状況を見比べて判断していた。
限度額と与信残高が分かれば可否は機械で決まるので、この判断を削除する。

    与信使用額 = 売掛残高 + 受注残 + 受取手形残 − 前受金
    与信枠     = 与信限度額 + 有効な一時増枠
    与信余力   = 与信枠 − 与信使用額

判定は4つ。

    approved         : 受注後も与信枠内
    warning          : 与信枠内だが利用率が `warning_ratio` 以上(枠の追加や回収督促の検討)
    rejected         : 受注により与信枠を超過
    blocked          : 滞留・貸倒事由により与信停止(枠が空いていても受注しない)
    requires_manual  : 与信限度額が未設定

要点は4つ。

    1. **受注残を与信使用額に含める**。売掛残高だけで判定すると、出荷・請求した瞬間に必ず枠を
       超える受注を通してしまう。前受金は既に受け取っているので控除する。
    2. **滞留していれば枠が空いていても止める**(`blocked`)。回収が遅れている相手に出荷を続けるのが
       貸倒れの典型的な発生経路で、`blocking_days_overdue` 以上の滞留と貸倒事由を停止条件にする。
       エイジング(#87)の `max_days_overdue` をそのまま渡せる。
    3. **限度額が未設定の取引先を自動承認しない**。0 と見なせば全件却下、無限と見なせば無審査に
       なるため `requires_manual` として人の判断に返す。
    4. **一時増枠は基準日で失効させる**。期限切れの増枠を枠に足したままにすると、実質的に限度額を
       引き上げたのと同じになる。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

JUDGMENT_APPROVED = "approved"
JUDGMENT_WARNING = "warning"
JUDGMENT_REJECTED = "rejected"
JUDGMENT_BLOCKED = "blocked"
JUDGMENT_MANUAL = "requires_manual"

REASON_WITHIN_LIMIT = "与信枠内"
REASON_HIGH_UTILIZATION = "与信枠内だが利用率が高い"
REASON_OVER_LIMIT = "与信枠を超過"
REASON_OVERDUE = "回収が滞留しているため与信停止"
REASON_DEFAULT_EVENT = "貸倒事由が発生しているため与信停止"
REASON_NO_LIMIT = "与信限度額が未設定"

DEFAULT_WARNING_RATIO = Decimal("0.8")
DEFAULT_BLOCKING_DAYS_OVERDUE = 61

_ZERO = Decimal("0")


@dataclass(frozen=True)
class CreditRequest:
    customer_code: str
    customer_name: str
    order_amount: Decimal = _ZERO
    credit_limit: Decimal | None = None
    receivable_balance: Decimal = _ZERO
    order_backlog: Decimal = _ZERO
    notes_receivable: Decimal = _ZERO
    advance_received: Decimal = _ZERO
    temporary_limit: Decimal = _ZERO
    temporary_limit_expiry: date | None = None
    max_days_overdue: int = 0
    has_default_event: bool = False


@dataclass(frozen=True)
class CreditJudgment:
    customer_code: str
    customer_name: str
    judgment: str
    reason: str
    credit_line: Decimal
    exposure: Decimal
    available_credit: Decimal
    order_amount: Decimal
    exposure_after_order: Decimal
    excess_amount: Decimal
    utilization_ratio: Decimal | None
    max_days_overdue: int


@dataclass(frozen=True)
class CreditCheckResult:
    as_of: date
    judgments: list[CreditJudgment]
    total_exposure: Decimal
    total_available_credit: Decimal
    blocked_customer_codes: list[str]
    rejected_customer_codes: list[str]
    manual_customer_codes: list[str]


class CreditLimitService:
    """与信限度額に対する受注可否を判定する純粋サービス。"""

    @staticmethod
    def _validate(request: CreditRequest) -> None:
        for name, value in (
            ("order_amount", request.order_amount),
            ("receivable_balance", request.receivable_balance),
            ("order_backlog", request.order_backlog),
            ("notes_receivable", request.notes_receivable),
            ("advance_received", request.advance_received),
            ("temporary_limit", request.temporary_limit),
        ):
            if value < _ZERO:
                raise ValueError(f"{name} must not be negative")
        if request.credit_limit is not None and request.credit_limit < _ZERO:
            raise ValueError("credit_limit must not be negative")
        if request.max_days_overdue < 0:
            raise ValueError("max_days_overdue must not be negative")
        if request.temporary_limit > _ZERO and request.temporary_limit_expiry is None:
            raise ValueError("一時増枠には temporary_limit_expiry が必要")

    @classmethod
    def _judge_one(
        cls,
        *,
        as_of: date,
        request: CreditRequest,
        warning_ratio: Decimal,
        blocking_days_overdue: int,
    ) -> CreditJudgment:
        cls._validate(request)

        exposure = (
            request.receivable_balance
            + request.order_backlog
            + request.notes_receivable
            - request.advance_received
        )
        temporary = _ZERO
        if (
            request.temporary_limit_expiry is not None
            and request.temporary_limit_expiry >= as_of
        ):
            temporary = request.temporary_limit
        credit_line = (request.credit_limit or _ZERO) + temporary
        available = credit_line - exposure
        after_order = exposure + request.order_amount
        excess = after_order - credit_line
        utilization = (
            (after_order / credit_line) if credit_line > _ZERO else None
        )

        if request.has_default_event:
            judgment, reason = JUDGMENT_BLOCKED, REASON_DEFAULT_EVENT
        elif request.max_days_overdue >= blocking_days_overdue:
            judgment, reason = JUDGMENT_BLOCKED, REASON_OVERDUE
        elif request.credit_limit is None:
            judgment, reason = JUDGMENT_MANUAL, REASON_NO_LIMIT
        elif excess > _ZERO:
            judgment, reason = JUDGMENT_REJECTED, REASON_OVER_LIMIT
        elif utilization is not None and utilization >= warning_ratio:
            judgment, reason = JUDGMENT_WARNING, REASON_HIGH_UTILIZATION
        else:
            judgment, reason = JUDGMENT_APPROVED, REASON_WITHIN_LIMIT

        return CreditJudgment(
            customer_code=request.customer_code,
            customer_name=request.customer_name,
            judgment=judgment,
            reason=reason,
            credit_line=credit_line,
            exposure=exposure,
            available_credit=available,
            order_amount=request.order_amount,
            exposure_after_order=after_order,
            excess_amount=max(excess, _ZERO),
            utilization_ratio=utilization,
            max_days_overdue=request.max_days_overdue,
        )

    @classmethod
    def check(
        cls,
        *,
        as_of: date,
        requests: list[CreditRequest],
        warning_ratio: Decimal = DEFAULT_WARNING_RATIO,
        blocking_days_overdue: int = DEFAULT_BLOCKING_DAYS_OVERDUE,
    ) -> CreditCheckResult:
        if not _ZERO < warning_ratio <= Decimal("1"):
            raise ValueError("warning_ratio must be within (0, 1]")
        if blocking_days_overdue <= 0:
            raise ValueError("blocking_days_overdue must be positive")
        codes = [request.customer_code for request in requests]
        if len(set(codes)) != len(codes):
            raise ValueError("customer_code must be unique")

        judgments = [
            cls._judge_one(
                as_of=as_of,
                request=request,
                warning_ratio=warning_ratio,
                blocking_days_overdue=blocking_days_overdue,
            )
            for request in requests
        ]

        def _codes(judgment: str) -> list[str]:
            return [item.customer_code for item in judgments if item.judgment == judgment]

        return CreditCheckResult(
            as_of=as_of,
            judgments=judgments,
            total_exposure=sum((item.exposure for item in judgments), _ZERO),
            total_available_credit=sum(
                (max(item.available_credit, _ZERO) for item in judgments),
                _ZERO,
            ),
            blocked_customer_codes=_codes(JUDGMENT_BLOCKED),
            rejected_customer_codes=_codes(JUDGMENT_REJECTED),
            manual_customer_codes=_codes(JUDGMENT_MANUAL),
        )
