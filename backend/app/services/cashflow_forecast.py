from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.models.models import Invoice, PaymentRequest


@dataclass(frozen=True)
class CashflowForecastBucket:
    horizon_days: int
    inflows: Decimal
    outflows: Decimal
    net_cashflow: Decimal


class CashflowForecastService:
    @staticmethod
    def forecast(
        *,
        company_id: UUID,
        as_of: date,
        invoices: list[Invoice],
        payment_requests: list[PaymentRequest],
        horizons: list[int],
    ) -> list[CashflowForecastBucket]:
        buckets: list[CashflowForecastBucket] = []
        for horizon in horizons:
            end_date = as_of + timedelta(days=horizon)
            inflows = sum(
                (
                    Decimal(str(inv.total_amount))
                    for inv in invoices
                    if inv.company_id == company_id
                    and inv.status in {"issued", "paid"}
                    and as_of <= inv.due_date <= end_date
                ),
                Decimal("0"),
            )
            outflows = sum(
                (
                    Decimal(str(req.payment_amount))
                    for req in payment_requests
                    if req.company_id == company_id
                    and req.status in {"approved", "executed"}
                    and as_of <= req.payment_date <= end_date
                ),
                Decimal("0"),
            )
            buckets.append(
                CashflowForecastBucket(
                    horizon_days=horizon,
                    inflows=inflows,
                    outflows=outflows,
                    net_cashflow=inflows - outflows,
                )
            )
        return buckets
