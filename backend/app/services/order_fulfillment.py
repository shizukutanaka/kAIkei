"""受注の出荷消化管理(売上計上明細の生成・受注残の集計・納期遅延の検知)。

与信チェック(#90)で受注可否まで自動化しても、承認後の受注は「いつ出荷され、どこまで売上に
なったか」を担当者が受注書と出荷伝票を突き合わせて管理していた。受注数量・単価と出荷実績が
あれば売上計上額も受注残も一意に決まるので、この工程を削除する。

    出荷金額   = 単価 × 出荷数量        (最終出荷は 受注総額 − 既計上額 で丸め差を吸収)
    受注残     = (受注数量 − 出荷済数量) × 単価
    売上計上日 = 出荷日                  (出荷基準)

要点は5つ。

    1. **売上は出荷日で計上する**(出荷基準)。受注日で計上すると出荷していない売上を立てることに
       なり期ズレ・架空売上になる。分納は出荷のつど計上する。
    2. **金額ではなく数量で消し込む**。出荷金額を人が入力すると受注残が端数で残り続ける。
       ただし単価×数量を出荷ごとに丸めると合計が受注総額とズレるため、**受注を満たす最終出荷では
       受注総額との差額を計上する**(残高が1円残る/超えるのを防ぐ)。
    3. **過剰出荷は受け付けない**。受注数量を超える出荷は受注変更が先で、黙って売上にすると
       請求できない売掛金が生まれる。
    4. **与信が通っていない受注は出荷指示に出さない**(`on_hold`)。#90 の判定をそのまま渡せる。
    5. **納期を過ぎた未出荷を検知する**。遅延は督促ではなく自社の履行義務なので、遅延日数付きで
       出荷指示に載せる。

生成した売上明細は `sales_closing` の `SalesLine` にそのまま渡せる形で返し、受注残は
`credit_limit` の `order_backlog` にそのまま渡せる。基準日は呼び出し側が渡す。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

STATUS_NOT_SHIPPED = "not_shipped"
STATUS_PARTIALLY_SHIPPED = "partially_shipped"
STATUS_COMPLETED = "completed"
STATUS_ON_HOLD = "on_hold"

CREDIT_APPROVED = "approved"
CREDIT_WARNING = "warning"
_SHIPPABLE_CREDIT = frozenset({CREDIT_APPROVED, CREDIT_WARNING})

_ZERO = Decimal("0")


@dataclass(frozen=True)
class Order:
    order_id: str
    customer_code: str
    customer_name: str
    order_date: date
    delivery_date: date
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal = Decimal("0.10")
    description: str = ""
    credit_status: str = CREDIT_APPROVED


@dataclass(frozen=True)
class Shipment:
    shipment_id: str
    order_id: str
    shipped_date: date
    quantity: Decimal


@dataclass(frozen=True)
class SalesEntry:
    line_id: str
    order_id: str
    customer_code: str
    customer_name: str
    sales_date: date
    quantity: Decimal
    amount: Decimal
    tax_rate: Decimal
    description: str


@dataclass(frozen=True)
class OrderProgress:
    order_id: str
    customer_code: str
    customer_name: str
    delivery_date: date
    status: str
    ordered_quantity: Decimal
    shipped_quantity: Decimal
    remaining_quantity: Decimal
    order_amount: Decimal
    recognized_amount: Decimal
    backlog_amount: Decimal
    last_shipped_date: date | None
    delay_days: int


@dataclass(frozen=True)
class CustomerBacklog:
    customer_code: str
    customer_name: str
    order_backlog: Decimal
    open_order_count: int


@dataclass(frozen=True)
class OrderFulfillmentResult:
    as_of: date
    orders: list[OrderProgress]
    sales_entries: list[SalesEntry]
    backlogs: list[CustomerBacklog]
    total_recognized_amount: Decimal
    total_backlog_amount: Decimal
    delayed_order_ids: list[str]
    on_hold_order_ids: list[str]


class OrderFulfillmentService:
    """受注と出荷実績から売上計上明細・受注残・納期遅延を導出する純粋サービス。"""

    @staticmethod
    def _round(amount: Decimal) -> Decimal:
        return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    @classmethod
    def process(
        cls,
        *,
        as_of: date,
        orders: list[Order],
        shipments: list[Shipment],
    ) -> OrderFulfillmentResult:
        order_ids = [order.order_id for order in orders]
        if len(set(order_ids)) != len(order_ids):
            raise ValueError("order_id must be unique")
        shipment_ids = [shipment.shipment_id for shipment in shipments]
        if len(set(shipment_ids)) != len(shipment_ids):
            raise ValueError("shipment_id must be unique")

        orders_by_id: dict[str, Order] = {}
        for order in orders:
            if order.quantity <= _ZERO:
                raise ValueError("quantity must be positive")
            if order.unit_price < _ZERO:
                raise ValueError("unit_price must not be negative")
            if order.delivery_date < order.order_date:
                raise ValueError("delivery_date must not precede order_date")
            orders_by_id[order.order_id] = order

        grouped: dict[str, list[Shipment]] = defaultdict(list)
        for shipment in shipments:
            if shipment.order_id not in orders_by_id:
                raise ValueError(f"受注が存在しない出荷: {shipment.shipment_id}")
            if shipment.quantity <= _ZERO:
                raise ValueError("shipment quantity must be positive")
            grouped[shipment.order_id].append(shipment)

        sales_entries: list[SalesEntry] = []
        progresses: list[OrderProgress] = []

        for order in orders:
            order_amount = cls._round(order.quantity * order.unit_price)
            shipped_quantity = _ZERO
            recognized = _ZERO
            last_shipped: date | None = None

            for shipment in sorted(
                grouped.get(order.order_id, []),
                key=lambda item: (item.shipped_date, item.shipment_id),
            ):
                shipped_quantity += shipment.quantity
                if shipped_quantity > order.quantity:
                    raise ValueError(f"受注数量を超える出荷: {shipment.shipment_id}")
                if shipped_quantity == order.quantity:
                    amount = order_amount - recognized  # 丸め差を最終出荷で吸収
                else:
                    amount = cls._round(shipment.quantity * order.unit_price)
                recognized += amount
                last_shipped = shipment.shipped_date
                sales_entries.append(
                    SalesEntry(
                        line_id=f"{order.order_id}-{shipment.shipment_id}",
                        order_id=order.order_id,
                        customer_code=order.customer_code,
                        customer_name=order.customer_name,
                        sales_date=shipment.shipped_date,
                        quantity=shipment.quantity,
                        amount=amount,
                        tax_rate=order.tax_rate,
                        description=order.description,
                    ),
                )

            remaining = order.quantity - shipped_quantity
            backlog = order_amount - recognized
            if remaining <= _ZERO:
                status = STATUS_COMPLETED
            elif order.credit_status not in _SHIPPABLE_CREDIT:
                status = STATUS_ON_HOLD
            elif shipped_quantity > _ZERO:
                status = STATUS_PARTIALLY_SHIPPED
            else:
                status = STATUS_NOT_SHIPPED

            delay_days = 0
            if status != STATUS_COMPLETED and order.delivery_date < as_of:
                delay_days = (as_of - order.delivery_date).days

            progresses.append(
                OrderProgress(
                    order_id=order.order_id,
                    customer_code=order.customer_code,
                    customer_name=order.customer_name,
                    delivery_date=order.delivery_date,
                    status=status,
                    ordered_quantity=order.quantity,
                    shipped_quantity=shipped_quantity,
                    remaining_quantity=remaining,
                    order_amount=order_amount,
                    recognized_amount=recognized,
                    backlog_amount=backlog,
                    last_shipped_date=last_shipped,
                    delay_days=delay_days,
                ),
            )

        sales_entries.sort(key=lambda entry: (entry.sales_date, entry.line_id))

        backlog_by_customer: dict[str, list[OrderProgress]] = defaultdict(list)
        for progress in progresses:
            if progress.backlog_amount > _ZERO:
                backlog_by_customer[progress.customer_code].append(progress)

        backlogs = [
            CustomerBacklog(
                customer_code=customer_code,
                customer_name=items[0].customer_name,
                order_backlog=sum((item.backlog_amount for item in items), _ZERO),
                open_order_count=len(items),
            )
            for customer_code, items in sorted(backlog_by_customer.items())
        ]

        return OrderFulfillmentResult(
            as_of=as_of,
            orders=progresses,
            sales_entries=sales_entries,
            backlogs=backlogs,
            total_recognized_amount=sum(
                (progress.recognized_amount for progress in progresses),
                _ZERO,
            ),
            total_backlog_amount=sum((backlog.order_backlog for backlog in backlogs), _ZERO),
            delayed_order_ids=[
                progress.order_id for progress in progresses if progress.delay_days > 0
            ],
            on_hold_order_ids=[
                progress.order_id
                for progress in progresses
                if progress.status == STATUS_ON_HOLD
            ],
        )
