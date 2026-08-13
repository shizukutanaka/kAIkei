"""受注の出荷消化管理(売上計上明細・受注残・納期遅延)のテスト。"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.order_fulfillment import (
    STATUS_COMPLETED,
    STATUS_NOT_SHIPPED,
    STATUS_ON_HOLD,
    STATUS_PARTIALLY_SHIPPED,
    Order,
    OrderFulfillmentService,
    Shipment,
)

AS_OF = date(2025, 9, 30)


def _order(**overrides: object) -> Order:
    base = {
        "order_id": "SO1",
        "customer_code": "C1",
        "customer_name": "山田商事",
        "order_date": date(2025, 9, 1),
        "delivery_date": date(2025, 10, 31),
        "quantity": Decimal("10"),
        "unit_price": Decimal("10000"),
    }
    base.update(overrides)
    return Order(**base)  # type: ignore[arg-type]


def _shipment(**overrides: object) -> Shipment:
    base = {
        "shipment_id": "SH1",
        "order_id": "SO1",
        "shipped_date": date(2025, 9, 10),
        "quantity": Decimal("4"),
    }
    base.update(overrides)
    return Shipment(**base)  # type: ignore[arg-type]


def _process(orders: list[Order], shipments: list[Shipment], as_of: date = AS_OF):
    return OrderFulfillmentService.process(as_of=as_of, orders=orders, shipments=shipments)


def test_empty_input_returns_zero_totals() -> None:
    result = _process([], [])
    assert result.orders == []
    assert result.sales_entries == []
    assert result.backlogs == []
    assert result.total_recognized_amount == Decimal("0")
    assert result.total_backlog_amount == Decimal("0")


def test_order_without_shipment_is_full_backlog() -> None:
    result = _process([_order()], [])
    progress = result.orders[0]
    assert progress.status == STATUS_NOT_SHIPPED
    assert progress.shipped_quantity == Decimal("0")
    assert progress.order_amount == Decimal("100000")
    assert progress.recognized_amount == Decimal("0")
    assert progress.backlog_amount == Decimal("100000")
    assert progress.last_shipped_date is None
    assert result.sales_entries == []
    assert result.total_backlog_amount == Decimal("100000")


def test_partial_shipment_recognizes_shipped_portion_only() -> None:
    result = _process([_order()], [_shipment()])
    progress = result.orders[0]
    assert progress.status == STATUS_PARTIALLY_SHIPPED
    assert progress.recognized_amount == Decimal("40000")
    assert progress.remaining_quantity == Decimal("6")
    assert progress.backlog_amount == Decimal("60000")
    assert progress.last_shipped_date == date(2025, 9, 10)
    entry = result.sales_entries[0]
    assert entry.line_id == "SO1-SH1"
    assert entry.sales_date == date(2025, 9, 10)
    assert entry.amount == Decimal("40000")
    assert entry.tax_rate == Decimal("0.10")


def test_full_shipment_completes_order() -> None:
    result = _process([_order()], [_shipment(quantity=Decimal("10"))])
    progress = result.orders[0]
    assert progress.status == STATUS_COMPLETED
    assert progress.remaining_quantity == Decimal("0")
    assert progress.backlog_amount == Decimal("0")
    assert result.backlogs == []
    assert result.total_recognized_amount == Decimal("100000")


def test_multiple_shipments_are_recognized_on_each_shipped_date() -> None:
    result = _process(
        [_order()],
        [
            _shipment(shipment_id="SH2", shipped_date=date(2025, 9, 20), quantity=Decimal("6")),
            _shipment(),
        ],
    )
    assert [entry.sales_date for entry in result.sales_entries] == [
        date(2025, 9, 10),
        date(2025, 9, 20),
    ]
    assert [entry.amount for entry in result.sales_entries] == [
        Decimal("40000"),
        Decimal("60000"),
    ]
    assert result.orders[0].status == STATUS_COMPLETED


def test_final_shipment_absorbs_rounding_difference() -> None:
    # 3 × 333.33 = 999.99 → 受注総額1000。行ごとに丸めると 333+333+333=999 で1円残る。
    order = _order(quantity=Decimal("3"), unit_price=Decimal("333.33"))
    shipments = [
        _shipment(shipment_id=f"SH{i}", shipped_date=date(2025, 9, 10 + i), quantity=Decimal("1"))
        for i in (1, 2, 3)
    ]
    result = _process([order], shipments)
    amounts = [entry.amount for entry in result.sales_entries]
    assert amounts == [Decimal("333"), Decimal("333"), Decimal("334")]
    assert sum(amounts) == result.orders[0].order_amount == Decimal("1000")
    assert result.orders[0].backlog_amount == Decimal("0")


def test_overdue_open_order_reports_delay_days() -> None:
    result = _process([_order(delivery_date=date(2025, 9, 20))], [_shipment()])
    assert result.orders[0].delay_days == 10
    assert result.delayed_order_ids == ["SO1"]


def test_completed_order_is_not_delayed() -> None:
    result = _process(
        [_order(delivery_date=date(2025, 9, 20))],
        [_shipment(quantity=Decimal("10"))],
    )
    assert result.orders[0].delay_days == 0
    assert result.delayed_order_ids == []


@pytest.mark.parametrize("credit_status", ["rejected", "blocked", "requires_manual"])
def test_non_shippable_credit_status_puts_order_on_hold(credit_status: str) -> None:
    result = _process([_order(credit_status=credit_status)], [])
    assert result.orders[0].status == STATUS_ON_HOLD
    assert result.on_hold_order_ids == ["SO1"]


@pytest.mark.parametrize("credit_status", ["approved", "warning"])
def test_shippable_credit_status_is_not_on_hold(credit_status: str) -> None:
    result = _process([_order(credit_status=credit_status)], [])
    assert result.orders[0].status == STATUS_NOT_SHIPPED
    assert result.on_hold_order_ids == []


def test_completed_order_is_not_on_hold_even_when_credit_failed() -> None:
    result = _process(
        [_order(credit_status="blocked")],
        [_shipment(quantity=Decimal("10"))],
    )
    assert result.orders[0].status == STATUS_COMPLETED
    assert result.on_hold_order_ids == []


def test_backlog_is_aggregated_per_customer() -> None:
    result = _process(
        [
            _order(),
            _order(order_id="SO2", quantity=Decimal("5")),
            _order(order_id="SO3", customer_code="C2", customer_name="佐藤商店"),
        ],
        [_shipment()],
    )
    assert [(b.customer_code, b.order_backlog, b.open_order_count) for b in result.backlogs] == [
        ("C1", Decimal("110000"), 2),
        ("C2", Decimal("100000"), 1),
    ]
    assert result.total_backlog_amount == Decimal("210000")
    assert result.total_recognized_amount == Decimal("40000")


def test_over_shipment_is_rejected() -> None:
    with pytest.raises(ValueError, match="受注数量を超える出荷"):
        _process([_order()], [_shipment(quantity=Decimal("11"))])


def test_shipment_for_unknown_order_is_rejected() -> None:
    with pytest.raises(ValueError, match="受注が存在しない出荷"):
        _process([_order()], [_shipment(order_id="SO9")])


def test_duplicate_order_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="order_id must be unique"):
        _process([_order(), _order()], [])


def test_duplicate_shipment_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="shipment_id must be unique"):
        _process([_order()], [_shipment(), _shipment(quantity=Decimal("1"))])


def test_delivery_date_before_order_date_is_rejected() -> None:
    with pytest.raises(ValueError, match="delivery_date"):
        _process([_order(delivery_date=date(2025, 8, 31))], [])


def test_non_positive_order_quantity_is_rejected() -> None:
    with pytest.raises(ValueError, match="quantity must be positive"):
        _process([_order(quantity=Decimal("0"))], [])


def test_negative_unit_price_is_rejected() -> None:
    with pytest.raises(ValueError, match="unit_price"):
        _process([_order(unit_price=Decimal("-1"))], [])


def test_non_positive_shipment_quantity_is_rejected() -> None:
    with pytest.raises(ValueError, match="shipment quantity must be positive"):
        _process([_order()], [_shipment(quantity=Decimal("0"))])


def test_result_is_serializable_by_response_schema() -> None:
    from app.schemas.schemas import OrderFulfillmentResponse

    result = _process([_order()], [_shipment()])
    payload = OrderFulfillmentResponse.model_validate(result)
    assert payload.orders[0].status == STATUS_PARTIALLY_SHIPPED
    assert payload.sales_entries[0].amount == Decimal("40000")
    assert payload.backlogs[0].order_backlog == Decimal("60000")
