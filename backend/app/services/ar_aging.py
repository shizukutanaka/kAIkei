"""売掛金年齢調べ（債権年齢表 / AR aging）。

未回収の請求書を支払期日からの経過日数で区分し、取引先別・区分別に集計する。
実務上の用途:
- 滞留債権の把握と回収管理（与信管理）。
- 貸倒引当金の見積り。金融商品会計基準では債権を「一般債権／貸倒懸念債権／
  破産更生債権等」に区分し、一般債権は貸倒実績率法で見積もるため、
  滞留期間別の残高集計が基礎資料となる。

区分は実務で一般的な「期日未到来 / 1-30日 / 31-60日 / 61-90日 / 90日超」。
DB非依存の純粋関数として実装し、集計ロジックを単体テスト可能にする。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

# 未回収とみなす請求書ステータス（発行済みのみ。下書き/入金済/取消は対象外）。
OPEN_INVOICE_STATUSES = ("issued",)

BUCKET_NOT_DUE = "not_due"
BUCKET_1_30 = "overdue_1_30"
BUCKET_31_60 = "overdue_31_60"
BUCKET_61_90 = "overdue_61_90"
BUCKET_OVER_90 = "overdue_over_90"

BUCKET_ORDER = (BUCKET_NOT_DUE, BUCKET_1_30, BUCKET_31_60, BUCKET_61_90, BUCKET_OVER_90)

BUCKET_LABELS = {
    BUCKET_NOT_DUE: "期日未到来",
    BUCKET_1_30: "1-30日超過",
    BUCKET_31_60: "31-60日超過",
    BUCKET_61_90: "61-90日超過",
    BUCKET_OVER_90: "90日超過",
}


def days_overdue(due_date: date, as_of: date) -> int:
    """支払期日からの経過日数。期日当日は0、未到来は負数。"""
    return (as_of - due_date).days


def classify_bucket(due_date: date, as_of: date) -> str:
    """支払期日と基準日から滞留区分を判定する。

    期日当日を含め経過日数が0以下なら「期日未到来」。以降は 1-30 / 31-60 / 61-90 / 90日超。
    """
    overdue = days_overdue(due_date, as_of)
    if overdue <= 0:
        return BUCKET_NOT_DUE
    if overdue <= 30:
        return BUCKET_1_30
    if overdue <= 60:
        return BUCKET_31_60
    if overdue <= 90:
        return BUCKET_61_90
    return BUCKET_OVER_90


@dataclass
class PartnerAging:
    partner_id: UUID | None
    partner_name: str
    buckets: dict[str, Decimal] = field(default_factory=lambda: {b: Decimal("0") for b in BUCKET_ORDER})
    total: Decimal = Decimal("0")
    invoice_count: int = 0
    oldest_days_overdue: int = 0


def _empty_buckets() -> dict[str, Decimal]:
    return {b: Decimal("0") for b in BUCKET_ORDER}


def aggregate_aging(invoices: list, as_of: date, partner_names: dict | None = None) -> dict:
    """未回収請求書を取引先別・滞留区分別に集計する。

    invoices は invoice_id/partner_id/due_date/total_amount/status 属性を持つ行
    （SQLAlchemyモデルでもダミーオブジェクトでも可）。
    """
    partner_names = partner_names or {}
    per_partner: dict[object, PartnerAging] = {}
    totals = _empty_buckets()
    grand_total = Decimal("0")
    total_count = 0

    for inv in invoices:
        if inv.status not in OPEN_INVOICE_STATUSES:
            continue
        amount = Decimal(str(inv.total_amount or 0))
        bucket = classify_bucket(inv.due_date, as_of)
        overdue = max(0, days_overdue(inv.due_date, as_of))

        key = inv.partner_id
        if key not in per_partner:
            per_partner[key] = PartnerAging(
                partner_id=inv.partner_id,
                partner_name=partner_names.get(inv.partner_id, "(取引先未設定)"),
                buckets=_empty_buckets(),
            )
        entry = per_partner[key]
        entry.buckets[bucket] += amount
        entry.total += amount
        entry.invoice_count += 1
        entry.oldest_days_overdue = max(entry.oldest_days_overdue, overdue)

        totals[bucket] += amount
        grand_total += amount
        total_count += 1

    # 残高の大きい順（同額なら滞留の長い順）に並べる
    partners = sorted(
        per_partner.values(), key=lambda p: (-p.total, -p.oldest_days_overdue)
    )
    return {
        "as_of": as_of,
        "buckets": totals,
        "total": grand_total,
        "invoice_count": total_count,
        "partners": partners,
        "overdue_total": grand_total - totals[BUCKET_NOT_DUE],
    }
