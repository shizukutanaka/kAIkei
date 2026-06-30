from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Invoice, PaymentRequest
from app.schemas.schemas import CashflowForecastBucket, CashflowForecastResponse
from app.services.cashflow_forecast import CashflowForecastService

router = APIRouter()


@router.get("/cashflow-forecast", response_model=CashflowForecastResponse)
async def cashflow_forecast(
    company_id: UUID = Query(...),  # noqa: B008
    as_of: date = Query(...),  # noqa: B008
    horizon_days: list[int] = Query(default=[7, 30, 90, 365]),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> CashflowForecastResponse:
    invoices = (
        await db.execute(
            select(Invoice).where(
                Invoice.company_id == company_id,
                Invoice.status.in_(("issued", "paid")),
            )
        )
    ).scalars().all()
    payment_requests = (
        await db.execute(
            select(PaymentRequest).where(
                PaymentRequest.company_id == company_id,
                PaymentRequest.status.in_(("approved", "executed")),
            )
        )
    ).scalars().all()
    buckets = CashflowForecastService.forecast(
        company_id=company_id,
        as_of=as_of,
        invoices=invoices,
        payment_requests=payment_requests,
        horizons=horizon_days,
    )
    return CashflowForecastResponse(
        company_id=company_id,
        as_of=as_of,
        buckets=[
            CashflowForecastBucket(
                horizon_days=bucket.horizon_days,
                inflows=bucket.inflows,
                outflows=bucket.outflows,
                net_cashflow=bucket.net_cashflow,
            )
            for bucket in buckets
        ],
    )
