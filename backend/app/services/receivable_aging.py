"""売掛金のエイジング(年齢調べ)と督促タスクの自動生成。

請求(#86)と消込(#84/#85)が自動で回っても、「入金予定日を過ぎたのに入っていない請求」を
見つけるのは担当者が期日一覧を目視で追う工程として残っていた。期日と残高が分かれば機械で決まる。

    残高 = 請求額 − 充当済額
    経過日数 = 基準日 − 入金予定日
    区分     = 未経過 / 1-30日 / 31-60日 / 61-90日 / 91日以上

督促は3点の判断を機械化する。

    1. **取引先単位にまとめる**。同じ相手に請求書の枚数だけ督促状を送るのは実務上の誤りで、
       最も古い滞留の段階に合わせて1件にする(段階: reminder → call → written_notice → legal)
    2. **少額の残骸で督促しない**。振込手数料差などの端数残で督促すると信用を毀損するため、
       `minimum_amount` 未満は督促対象から外す(エイジングには残す。残高は消さない)
    3. **消滅時効(民法166条1項・権利行使できると知った時から5年)を警告する**。
       5年経過で回収不能になるため、期限まで `statute_alert_days` を切ったら警告を立てる

区分別合計はそのまま貸倒引当金(#66)の一括評価金銭債権の入力になる。基準日は呼び出し側が渡す
(サーバ時刻に依存すると同じ入力でも結果が変わり、テストも監査もできない)。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

BUCKET_NOT_DUE = "not_due"
BUCKET_1_30 = "overdue_1_30"
BUCKET_31_60 = "overdue_31_60"
BUCKET_61_90 = "overdue_61_90"
BUCKET_91_PLUS = "overdue_91_plus"

BUCKET_ORDER = (
    BUCKET_NOT_DUE,
    BUCKET_1_30,
    BUCKET_31_60,
    BUCKET_61_90,
    BUCKET_91_PLUS,
)

ACTION_NONE = "none"
ACTION_REMINDER = "reminder"
ACTION_CALL = "call"
ACTION_WRITTEN_NOTICE = "written_notice"
ACTION_LEGAL = "legal"

_ESCALATION: dict[str, str] = {
    BUCKET_1_30: ACTION_REMINDER,
    BUCKET_31_60: ACTION_CALL,
    BUCKET_61_90: ACTION_WRITTEN_NOTICE,
    BUCKET_91_PLUS: ACTION_LEGAL,
}

_ACTION_TITLE: dict[str, str] = {
    ACTION_REMINDER: "入金督促(メール)",
    ACTION_CALL: "入金督促(電話・支払期日の確認)",
    ACTION_WRITTEN_NOTICE: "督促状の送付・与信停止の検討",
    ACTION_LEGAL: "内容証明・法的手続きの検討",
}

# 督促タスクの対応期限(基準日からの日数)。滞留が長いほど短くする。
_ACTION_LEAD_DAYS: dict[str, int] = {
    ACTION_REMINDER: 7,
    ACTION_CALL: 3,
    ACTION_WRITTEN_NOTICE: 2,
    ACTION_LEGAL: 1,
}

STATUTE_OF_LIMITATIONS_YEARS = 5
DEFAULT_STATUTE_ALERT_DAYS = 180

_ZERO = Decimal("0")


@dataclass(frozen=True)
class ReceivableItem:
    invoice_id: str
    customer_code: str
    customer_name: str
    due_date: date
    amount: Decimal
    paid_amount: Decimal = _ZERO


@dataclass(frozen=True)
class AgedReceivable:
    invoice_id: str
    customer_code: str
    customer_name: str
    due_date: date
    outstanding: Decimal
    days_overdue: int
    bucket: str
    statute_expiry_date: date
    statute_alert: bool


@dataclass(frozen=True)
class BucketSummary:
    bucket: str
    count: int
    amount: Decimal


@dataclass(frozen=True)
class CollectionTask:
    customer_code: str
    customer_name: str
    action: str
    title: str
    invoice_ids: list[str]
    outstanding: Decimal
    oldest_due_date: date
    max_days_overdue: int
    task_due_date: date
    statute_alert: bool


@dataclass(frozen=True)
class ReceivableAgingResult:
    as_of: date
    items: list[AgedReceivable]
    summary: list[BucketSummary]
    tasks: list[CollectionTask]
    total_outstanding: Decimal
    total_overdue: Decimal
    overdue_count: int


class ReceivableAgingService:
    """売掛金の滞留状況を区分し、取引先単位の督促タスクを生成する純粋サービス。"""

    @staticmethod
    def bucket_of(days_overdue: int) -> str:
        if days_overdue <= 0:
            return BUCKET_NOT_DUE
        if days_overdue <= 30:
            return BUCKET_1_30
        if days_overdue <= 60:
            return BUCKET_31_60
        if days_overdue <= 90:
            return BUCKET_61_90
        return BUCKET_91_PLUS

    @staticmethod
    def statute_expiry(due_date: date) -> date:
        """消滅時効の完成日(民法166条1項1号・5年)。"""
        try:
            return due_date.replace(year=due_date.year + STATUTE_OF_LIMITATIONS_YEARS)
        except ValueError:  # 2/29 の5年後は存在しないため 2/28 とする
            return due_date.replace(year=due_date.year + STATUTE_OF_LIMITATIONS_YEARS, day=28)

    @classmethod
    def analyze(
        cls,
        *,
        as_of: date,
        receivables: list[ReceivableItem],
        minimum_amount: Decimal = _ZERO,
        statute_alert_days: int = DEFAULT_STATUTE_ALERT_DAYS,
    ) -> ReceivableAgingResult:
        if minimum_amount < _ZERO:
            raise ValueError("minimum_amount must not be negative")
        if statute_alert_days < 0:
            raise ValueError("statute_alert_days must not be negative")
        invoice_ids = [item.invoice_id for item in receivables]
        if len(set(invoice_ids)) != len(invoice_ids):
            raise ValueError("invoice_id must be unique")

        items: list[AgedReceivable] = []
        for receivable in receivables:
            if receivable.amount <= _ZERO:
                raise ValueError("amount must be positive")
            if receivable.paid_amount < _ZERO:
                raise ValueError("paid_amount must not be negative")
            if receivable.paid_amount > receivable.amount:
                raise ValueError("paid_amount must not exceed amount")
            outstanding = receivable.amount - receivable.paid_amount
            if outstanding <= _ZERO:
                continue
            days_overdue = (as_of - receivable.due_date).days
            expiry = cls.statute_expiry(receivable.due_date)
            items.append(
                AgedReceivable(
                    invoice_id=receivable.invoice_id,
                    customer_code=receivable.customer_code,
                    customer_name=receivable.customer_name,
                    due_date=receivable.due_date,
                    outstanding=outstanding,
                    days_overdue=max(days_overdue, 0),
                    bucket=cls.bucket_of(days_overdue),
                    statute_expiry_date=expiry,
                    statute_alert=(expiry - as_of).days <= statute_alert_days,
                ),
            )

        items.sort(key=lambda item: (-item.days_overdue, item.invoice_id))

        grouped: dict[str, list[AgedReceivable]] = defaultdict(list)
        for item in items:
            if item.bucket == BUCKET_NOT_DUE or item.outstanding < minimum_amount:
                continue
            grouped[item.customer_code].append(item)

        tasks: list[CollectionTask] = []
        for customer_code, overdue_items in grouped.items():
            worst = max(overdue_items, key=lambda item: item.days_overdue)
            action = _ESCALATION[worst.bucket]
            tasks.append(
                CollectionTask(
                    customer_code=customer_code,
                    customer_name=worst.customer_name,
                    action=action,
                    title=_ACTION_TITLE[action],
                    invoice_ids=sorted(item.invoice_id for item in overdue_items),
                    outstanding=sum((item.outstanding for item in overdue_items), _ZERO),
                    oldest_due_date=min(item.due_date for item in overdue_items),
                    max_days_overdue=worst.days_overdue,
                    task_due_date=as_of + timedelta(days=_ACTION_LEAD_DAYS[action]),
                    statute_alert=any(item.statute_alert for item in overdue_items),
                ),
            )
        tasks.sort(key=lambda task: (-task.max_days_overdue, task.customer_code))

        summary = [
            BucketSummary(
                bucket=bucket,
                count=sum(1 for item in items if item.bucket == bucket),
                amount=sum(
                    (item.outstanding for item in items if item.bucket == bucket),
                    _ZERO,
                ),
            )
            for bucket in BUCKET_ORDER
        ]
        overdue_items = [item for item in items if item.bucket != BUCKET_NOT_DUE]

        return ReceivableAgingResult(
            as_of=as_of,
            items=items,
            summary=summary,
            tasks=tasks,
            total_outstanding=sum((item.outstanding for item in items), _ZERO),
            total_overdue=sum((item.outstanding for item in overdue_items), _ZERO),
            overdue_count=len(overdue_items),
        )
