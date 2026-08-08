from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.services.ar_aging import (
    BUCKET_1_30,
    BUCKET_31_60,
    BUCKET_61_90,
    BUCKET_NOT_DUE,
    BUCKET_OVER_90,
    aggregate_aging,
    classify_bucket,
    days_overdue,
)

AS_OF = date(2026, 6, 30)


@dataclass
class FakeInvoice:
    due_date: date
    total_amount: Decimal
    status: str = "issued"
    partner_id: object = None
    invoice_id: object = None


class TestClassifyBucket:
    def test_future_due_date_is_not_due(self):
        assert classify_bucket(date(2026, 7, 15), AS_OF) == BUCKET_NOT_DUE

    def test_due_today_is_not_due(self):
        # 期日当日はまだ延滞ではない
        assert classify_bucket(AS_OF, AS_OF) == BUCKET_NOT_DUE

    def test_boundaries_are_inclusive_upper(self):
        assert classify_bucket(date(2026, 6, 29), AS_OF) == BUCKET_1_30      # 1日
        assert classify_bucket(date(2026, 5, 31), AS_OF) == BUCKET_1_30      # 30日
        assert classify_bucket(date(2026, 5, 30), AS_OF) == BUCKET_31_60     # 31日
        assert classify_bucket(date(2026, 5, 1), AS_OF) == BUCKET_31_60      # 60日
        assert classify_bucket(date(2026, 4, 30), AS_OF) == BUCKET_61_90     # 61日
        assert classify_bucket(date(2026, 4, 1), AS_OF) == BUCKET_61_90      # 90日
        assert classify_bucket(date(2026, 3, 31), AS_OF) == BUCKET_OVER_90   # 91日

    def test_days_overdue_sign(self):
        assert days_overdue(date(2026, 6, 29), AS_OF) == 1
        assert days_overdue(AS_OF, AS_OF) == 0
        assert days_overdue(date(2026, 7, 10), AS_OF) == -10


class TestAggregateAging:
    def test_empty(self):
        result = aggregate_aging([], AS_OF)
        assert result["total"] == Decimal("0")
        assert result["invoice_count"] == 0
        assert result["partners"] == []
        assert result["overdue_total"] == Decimal("0")

    def test_only_issued_invoices_counted(self):
        p = uuid4()
        invoices = [
            FakeInvoice(date(2026, 5, 1), Decimal("10000"), "issued", p),
            FakeInvoice(date(2026, 5, 1), Decimal("99999"), "paid", p),
            FakeInvoice(date(2026, 5, 1), Decimal("88888"), "draft", p),
            FakeInvoice(date(2026, 5, 1), Decimal("77777"), "cancelled", p),
        ]
        result = aggregate_aging(invoices, AS_OF)
        assert result["total"] == Decimal("10000")
        assert result["invoice_count"] == 1

    def test_buckets_and_totals(self):
        p = uuid4()
        invoices = [
            FakeInvoice(date(2026, 7, 10), Decimal("1000"), "issued", p),   # 未到来
            FakeInvoice(date(2026, 6, 20), Decimal("2000"), "issued", p),   # 10日
            FakeInvoice(date(2026, 5, 20), Decimal("3000"), "issued", p),   # 41日
            FakeInvoice(date(2026, 4, 20), Decimal("4000"), "issued", p),   # 71日
            FakeInvoice(date(2026, 1, 20), Decimal("5000"), "issued", p),   # 161日
        ]
        r = aggregate_aging(invoices, AS_OF)
        assert r["buckets"][BUCKET_NOT_DUE] == Decimal("1000")
        assert r["buckets"][BUCKET_1_30] == Decimal("2000")
        assert r["buckets"][BUCKET_31_60] == Decimal("3000")
        assert r["buckets"][BUCKET_61_90] == Decimal("4000")
        assert r["buckets"][BUCKET_OVER_90] == Decimal("5000")
        assert r["total"] == Decimal("15000")
        # 延滞合計は総額から期日未到来を除いたもの
        assert r["overdue_total"] == Decimal("14000")

    def test_groups_by_partner_and_sorts_by_balance_desc(self):
        small, big = uuid4(), uuid4()
        invoices = [
            FakeInvoice(date(2026, 6, 1), Decimal("500"), "issued", small),
            FakeInvoice(date(2026, 6, 1), Decimal("9000"), "issued", big),
        ]
        names = {small: "小口商事", big: "大口物産"}
        r = aggregate_aging(invoices, AS_OF, partner_names=names)
        assert [p.partner_name for p in r["partners"]] == ["大口物産", "小口商事"]
        assert r["partners"][0].total == Decimal("9000")

    def test_partner_rollup_and_oldest_overdue(self):
        p = uuid4()
        invoices = [
            FakeInvoice(date(2026, 6, 20), Decimal("2000"), "issued", p),   # 10日
            FakeInvoice(date(2026, 1, 20), Decimal("5000"), "issued", p),   # 161日
        ]
        r = aggregate_aging(invoices, AS_OF, partner_names={p: "テスト商事"})
        entry = r["partners"][0]
        assert entry.total == Decimal("7000")
        assert entry.invoice_count == 2
        assert entry.oldest_days_overdue == 161

    def test_missing_partner_gets_placeholder_name(self):
        r = aggregate_aging([FakeInvoice(date(2026, 6, 1), Decimal("100"), "issued", None)], AS_OF)
        assert r["partners"][0].partner_name == "(取引先未設定)"

    def test_bucket_sum_equals_total(self):
        p = uuid4()
        invoices = [
            FakeInvoice(date(2026, 7, 5), Decimal("111"), "issued", p),
            FakeInvoice(date(2026, 6, 10), Decimal("222"), "issued", p),
            FakeInvoice(date(2026, 2, 10), Decimal("333"), "issued", p),
        ]
        r = aggregate_aging(invoices, AS_OF)
        assert sum(r["buckets"].values()) == r["total"] == Decimal("666")
