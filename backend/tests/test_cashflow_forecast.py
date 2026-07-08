from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.services.cashflow_forecast import CashflowForecastService


def _invoice(company_id, due_date, total_amount, status):
    return SimpleNamespace(
        company_id=company_id,
        due_date=due_date,
        total_amount=Decimal(str(total_amount)),
        status=status,
    )


def _payment_request(company_id, payment_date, payment_amount, status):
    return SimpleNamespace(
        company_id=company_id,
        payment_date=payment_date,
        payment_amount=Decimal(str(payment_amount)),
        status=status,
    )


class TestCashflowForecastService:
    def test_forecast_filters_by_window_status_and_calculates_net_cashflow(self):
        company_id = uuid4()
        other_company_id = uuid4()
        as_of = date(2026, 6, 1)

        invoices = [
            _invoice(company_id, date(2026, 6, 2), "100", "issued"),
            _invoice(company_id, date(2026, 6, 8), "200", "paid"),
            _invoice(company_id, date(2026, 6, 20), "300", "issued"),
            _invoice(company_id, date(2026, 8, 1), "400", "paid"),
            _invoice(company_id, date(2026, 6, 5), "999", "draft"),
            _invoice(other_company_id, date(2026, 6, 5), "1000", "issued"),
        ]
        payment_requests = [
            _payment_request(company_id, date(2026, 6, 1), "50", "approved"),
            _payment_request(company_id, date(2026, 6, 8), "75", "executed"),
            _payment_request(company_id, date(2026, 7, 1), "125", "approved"),
            _payment_request(company_id, date(2026, 7, 15), "999", "rejected"),
            _payment_request(other_company_id, date(2026, 6, 4), "2000", "approved"),
        ]

        buckets = CashflowForecastService.forecast(
            company_id=company_id,
            as_of=as_of,
            invoices=invoices,
            payment_requests=payment_requests,
            horizons=[7, 30, 90],
        )

        assert [bucket.horizon_days for bucket in buckets] == [7, 30, 90]
        assert buckets[0].inflows == Decimal("300")
        assert buckets[0].outflows == Decimal("125")
        assert buckets[0].net_cashflow == Decimal("175")

        assert buckets[1].inflows == Decimal("600")
        assert buckets[1].outflows == Decimal("250")
        assert buckets[1].net_cashflow == Decimal("350")

        assert buckets[2].inflows == Decimal("1000")
        assert buckets[2].outflows == Decimal("250")
        assert buckets[2].net_cashflow == Decimal("750")
