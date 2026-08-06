from datetime import date
from decimal import Decimal

import pytest

from app.schemas.schemas import ReceivableAgingResponse
from app.services.receivable_aging import (
    ACTION_CALL,
    ACTION_LEGAL,
    ACTION_REMINDER,
    ACTION_WRITTEN_NOTICE,
    BUCKET_1_30,
    BUCKET_31_60,
    BUCKET_61_90,
    BUCKET_91_PLUS,
    BUCKET_NOT_DUE,
    ReceivableAgingService,
    ReceivableItem,
)

AS_OF = date(2025, 9, 30)


def _item(
    invoice_id: str,
    due: str,
    amount: str = "110000",
    *,
    customer: str = "C1",
    paid: str = "0",
) -> ReceivableItem:
    return ReceivableItem(
        invoice_id=invoice_id,
        customer_code=customer,
        customer_name=f"{customer}商事",
        due_date=date.fromisoformat(due),
        amount=Decimal(amount),
        paid_amount=Decimal(paid),
    )


def _analyze(items, **kwargs):
    return ReceivableAgingService.analyze(as_of=AS_OF, receivables=items, **kwargs)


def _bucket(result, bucket: str):
    return next(s for s in result.summary if s.bucket == bucket)


def test_buckets_are_assigned_by_days_overdue():
    result = _analyze(
        [
            _item("I0", "2025-10-31"),
            _item("I1", "2025-09-15"),
            _item("I2", "2025-08-15"),
            _item("I3", "2025-07-15"),
            _item("I4", "2025-05-15"),
        ],
    )
    assert {i.invoice_id: i.bucket for i in result.items} == {
        "I0": BUCKET_NOT_DUE,
        "I1": BUCKET_1_30,
        "I2": BUCKET_31_60,
        "I3": BUCKET_61_90,
        "I4": BUCKET_91_PLUS,
    }
    assert result.overdue_count == 4
    assert result.total_outstanding == Decimal("550000")
    assert result.total_overdue == Decimal("440000")


def test_bucket_boundaries_are_inclusive():
    result = _analyze([_item("I1", "2025-08-31"), _item("I2", "2025-08-30")])
    by_id = {i.invoice_id: i for i in result.items}
    assert by_id["I1"].days_overdue == 30
    assert by_id["I1"].bucket == BUCKET_1_30
    assert by_id["I2"].days_overdue == 31
    assert by_id["I2"].bucket == BUCKET_31_60


def test_due_today_is_not_overdue():
    result = _analyze([_item("I1", "2025-09-30")])
    assert result.items[0].bucket == BUCKET_NOT_DUE
    assert result.items[0].days_overdue == 0
    assert result.tasks == []


def test_partially_paid_invoice_uses_outstanding_balance():
    result = _analyze([_item("I1", "2025-08-15", "110000", paid="40000")])
    assert result.items[0].outstanding == Decimal("70000")
    assert result.tasks[0].outstanding == Decimal("70000")


def test_fully_paid_invoice_is_excluded():
    result = _analyze([_item("I1", "2025-08-15", "110000", paid="110000")])
    assert result.items == []
    assert result.tasks == []
    assert result.total_outstanding == Decimal("0")


def test_tasks_are_grouped_per_customer_at_worst_stage():
    result = _analyze(
        [
            _item("I1", "2025-09-15"),
            _item("I2", "2025-07-15"),
            _item("I3", "2025-08-15", customer="C2"),
        ],
    )
    assert len(result.tasks) == 2
    first = result.tasks[0]
    assert first.customer_code == "C1"
    # 同じ相手に督促を2通出さず、最も古い滞留の段階に合わせて1件にまとめる
    assert first.invoice_ids == ["I1", "I2"]
    assert first.action == ACTION_WRITTEN_NOTICE
    assert first.outstanding == Decimal("220000")
    assert first.oldest_due_date == date(2025, 7, 15)
    assert result.tasks[1].customer_code == "C2"
    assert result.tasks[1].action == ACTION_CALL


def test_escalation_and_task_due_dates():
    result = _analyze(
        [
            _item("I1", "2025-09-15"),
            _item("I2", "2025-08-15", customer="C2"),
            _item("I3", "2025-07-15", customer="C3"),
            _item("I4", "2025-05-15", customer="C4"),
        ],
    )
    by_customer = {t.customer_code: t for t in result.tasks}
    assert by_customer["C1"].action == ACTION_REMINDER
    assert by_customer["C1"].task_due_date == date(2025, 10, 7)
    assert by_customer["C2"].action == ACTION_CALL
    assert by_customer["C2"].task_due_date == date(2025, 10, 3)
    assert by_customer["C3"].action == ACTION_WRITTEN_NOTICE
    assert by_customer["C3"].task_due_date == date(2025, 10, 2)
    assert by_customer["C4"].action == ACTION_LEGAL
    assert by_customer["C4"].task_due_date == date(2025, 10, 1)


def test_small_remainder_does_not_trigger_collection():
    result = _analyze(
        [_item("I1", "2025-08-15", "550"), _item("I2", "2025-08-15", "110000", customer="C2")],
        minimum_amount=Decimal("1000"),
    )
    # 端数残はエイジングには残すが督促しない(信用毀損を避ける)
    assert {i.invoice_id for i in result.items} == {"I1", "I2"}
    assert [t.customer_code for t in result.tasks] == ["C2"]


def test_statute_of_limitations_alert():
    result = _analyze([_item("I1", "2020-11-30"), _item("I2", "2021-06-30")])
    by_id = {i.invoice_id: i for i in result.items}
    assert by_id["I1"].statute_expiry_date == date(2025, 11, 30)
    assert by_id["I1"].statute_alert is True
    assert by_id["I2"].statute_expiry_date == date(2026, 6, 30)
    assert by_id["I2"].statute_alert is False
    assert next(t for t in result.tasks if "I1" in t.invoice_ids).statute_alert is True


def test_leap_day_statute_expiry_falls_back_to_28th():
    assert ReceivableAgingService.statute_expiry(date(2024, 2, 29)) == date(2029, 2, 28)


def test_summary_totals_per_bucket():
    result = _analyze([_item("I1", "2025-09-15"), _item("I2", "2025-09-20", "50000")])
    assert _bucket(result, BUCKET_1_30).count == 2
    assert _bucket(result, BUCKET_1_30).amount == Decimal("160000")
    assert _bucket(result, BUCKET_91_PLUS).count == 0
    assert _bucket(result, BUCKET_91_PLUS).amount == Decimal("0")


def test_invalid_input_rejected():
    with pytest.raises(ValueError, match="invoice_id"):
        _analyze([_item("I1", "2025-08-15"), _item("I1", "2025-08-16")])
    with pytest.raises(ValueError, match="amount must be positive"):
        _analyze([_item("I1", "2025-08-15", "0")])
    with pytest.raises(ValueError, match="paid_amount must not exceed"):
        _analyze([_item("I1", "2025-08-15", "1000", paid="2000")])
    with pytest.raises(ValueError, match="minimum_amount"):
        _analyze([_item("I1", "2025-08-15")], minimum_amount=Decimal("-1"))
    with pytest.raises(ValueError, match="statute_alert_days"):
        _analyze([_item("I1", "2025-08-15")], statute_alert_days=-1)


def test_empty_input():
    result = _analyze([])
    assert result.items == []
    assert result.tasks == []
    assert result.total_overdue == Decimal("0")
    assert len(result.summary) == 5


def test_response_schema_serializes_dataclass():
    result = _analyze([_item("I1", "2025-07-15")])
    payload = ReceivableAgingResponse.model_validate(result)
    assert payload.items[0].bucket == BUCKET_61_90
    assert payload.tasks[0].action == ACTION_WRITTEN_NOTICE
