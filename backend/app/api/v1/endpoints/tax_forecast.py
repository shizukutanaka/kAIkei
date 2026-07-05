from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.reports import PL_ACCOUNT_TYPES, _get_account_balances
from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.schemas.schemas import TaxForecastResponse
from app.services.income_tax import IncomeTaxService
from app.services.interim_consumption_tax import InterimConsumptionTaxService
from app.services.interim_corporate_tax import InterimCorporateTaxService
from app.services.local_consumption_tax import LocalConsumptionTaxService
from app.services.simplified_consumption_tax import SimplifiedConsumptionTaxService
from app.services.tax_forecast import DEFAULT_FORECAST_FACTOR, TaxForecastService
from app.services.withholding_tax import WithholdingTaxService

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


@router.get("/withholding-professional-fee")
async def get_withholding_professional_fee(
    amount: Decimal = Query(..., description="報酬額"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal]:
    try:
        withholding_tax = WithholdingTaxService.compute_professional_fee(amount)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "amount": amount,
        "withholding_tax": withholding_tax,
        "net_payment": amount - withholding_tax,
    }


@router.get("/simplified-consumption")
async def get_simplified_consumption_tax(
    sales_tax: Decimal = Query(..., description="売上税額"),  # noqa: B008
    business_category: int = Query(..., description="事業区分"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal | int]:
    try:
        result = SimplifiedConsumptionTaxService.compute(sales_tax, business_category)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "sales_tax": sales_tax,
        "business_category": result.business_category,
        "deemed_purchase_rate": result.deemed_purchase_rate,
        "deductible_tax": result.deductible_tax,
        "net_tax": result.net_tax,
    }


@router.get("/income-tax")
async def get_income_tax(
    taxable_income: Decimal = Query(..., description="課税所得金額"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal]:
    try:
        rounded_taxable_income = (taxable_income // Decimal("1000")) * Decimal("1000")
        income_tax = IncomeTaxService.compute(taxable_income)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "taxable_income": taxable_income,
        "rounded_taxable_income": rounded_taxable_income,
        "income_tax": income_tax,
    }


@router.get("/interim-consumption")
async def get_interim_consumption_tax(
    prior_year_national_tax: Decimal = Query(..., description="前年度の国税分消費税額"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal | int]:
    try:
        result = InterimConsumptionTaxService.compute(prior_year_national_tax)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "prior_year_national_tax": result.annualized_basis,
        "installment_count": result.installment_count,
        "per_installment": result.per_installment,
        "total_interim": result.total_interim,
    }


@router.get("/interim-corporate")
async def get_interim_corporate_tax(
    prior_year_corporate_tax: Decimal = Query(..., description="前期法人税額"),  # noqa: B008
    prior_period_months: int = Query(12, ge=1, le=12, description="前期月数"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal | int | bool]:
    try:
        result = InterimCorporateTaxService.compute(prior_year_corporate_tax, prior_period_months=prior_period_months)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "prior_year_corporate_tax": prior_year_corporate_tax,
        "prior_period_months": result.prior_period_months,
        "interim_tax": result.interim_tax,
        "filing_required": result.filing_required,
    }


@router.get("/local-consumption")
async def get_local_consumption_tax(
    national_tax: Decimal = Query(..., description="国税分消費税額"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal]:
    try:
        result = LocalConsumptionTaxService.compute(national_tax)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "national_tax": result.national_tax,
        "local_tax": result.local_tax,
        "total_tax": result.total_tax,
    }
