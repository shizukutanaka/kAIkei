from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.reports import PL_ACCOUNT_TYPES, _get_account_balances
from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.schemas.schemas import TaxForecastResponse
from app.services.tax_forecast import DEFAULT_FORECAST_FACTOR, TaxForecastService

router = APIRouter()


@router.get("/forecast", response_model=TaxForecastResponse)
async def get_tax_forecast(
    company_id: UUID = Query(..., description="会社ID"),  # noqa: B008
    forecast_factor: Decimal = Query(DEFAULT_FORECAST_FACTOR, description="年換算係数"),  # noqa: B008
    as_of: date | None = Query(None, description="基準日"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> TaxForecastResponse:
    as_of_date = as_of or date.today()
    rows = await _get_account_balances(db, company_id, as_of_date, PL_ACCOUNT_TYPES)

    total_revenue = Decimal("0")
    total_expense = Decimal("0")

    for row in rows:
        debit_sum = Decimal(row.debit_sum) if row.debit_sum else Decimal("0")
        credit_sum = Decimal(row.credit_sum) if row.credit_sum else Decimal("0")

        if row.account_type == "revenue":
            total_revenue += credit_sum - debit_sum
        elif row.account_type == "expense":
            total_expense += debit_sum - credit_sum

    result = TaxForecastService.forecast(
        total_revenue=total_revenue,
        total_expense=total_expense,
        forecast_factor=forecast_factor,
    )
    return TaxForecastResponse(
        forecasted_profit_before_tax=result.forecasted_profit_before_tax,
        estimated_taxable_income=result.estimated_taxable_income,
        estimated_tax_amount=result.estimated_tax_amount,
        tax_risk_warnings=result.tax_risk_warnings,
    )
