from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.reports import PL_ACCOUNT_TYPES, _get_account_balances
from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.schemas.schemas import (
    BadDebtAssessmentRequest,
    BadDebtAssessmentResponse,
    BadDebtJournalRequest,
    BadDebtJournalResponse,
    DebtorReceivableSchema,
    SalesReturnTaxRequest,
    SalesReturnTaxResponse,
    TaxForecastResponse,
)
from app.services.bad_debt_assessment import BadDebtAssessmentService, DebtorReceivable
from app.services.bad_debt_consumption_tax import BadDebtConsumptionTaxService
from app.services.bad_debt_journal_draft import BadDebtJournalDraftService
from app.services.bad_debt_reserve import BadDebtReserveService
from app.services.business_tax import BusinessTaxService
from app.services.corporate_tax import CorporateTaxService
from app.services.entertainment_expense import EntertainmentExpenseService
from app.services.income_tax import IncomeTaxService
from app.services.interim_consumption_tax import InterimConsumptionTaxService
from app.services.interim_corporate_tax import InterimCorporateTaxService
from app.services.invoice_transitional_deduction import InvoiceTransitionalDeductionService
from app.services.local_consumption_tax import LocalConsumptionTaxService
from app.services.local_corporate_tax import LocalCorporateTaxService
from app.services.purchase_tax_credit import PurchaseTaxCreditService
from app.services.sales_return_tax import SalesReturnLine, SalesReturnTaxService
from app.services.simplified_consumption_tax import SimplifiedConsumptionTaxService
from app.services.special_20_percent_consumption_tax import SpecialTwentyPercentConsumptionTaxService
from app.services.tax_forecast import DEFAULT_FORECAST_FACTOR, TaxForecastService
from app.services.taxable_enterprise import TaxableEnterpriseJudgmentService
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


@router.get("/special-20-percent")
async def get_special_20_percent_consumption_tax(
    sales_consumption_tax: Decimal = Query(..., description="課税売上に係る消費税額"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal]:
    try:
        result = SpecialTwentyPercentConsumptionTaxService.compute(sales_consumption_tax)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "sales_consumption_tax": result.sales_consumption_tax,
        "payable_tax": result.payable_tax,
        "special_deduction": result.special_deduction,
    }


@router.get("/purchase-tax-credit")
async def get_purchase_tax_credit(
    taxable_sales: Decimal = Query(..., description="課税売上高(税抜・免税売上含む)"),  # noqa: B008
    non_taxable_sales: Decimal = Query(..., description="非課税売上高"),  # noqa: B008
    input_tax_taxable_only: Decimal = Query(..., description="課税売上にのみ要する課税仕入等の税額"),  # noqa: B008
    input_tax_common: Decimal = Query(..., description="共通して要する課税仕入等の税額"),  # noqa: B008
    input_tax_nontaxable_only: Decimal = Query(Decimal("0"), description="非課税売上にのみ要する課税仕入等の税額"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal | bool]:
    try:
        result = PurchaseTaxCreditService.compute(
            taxable_sales=taxable_sales,
            non_taxable_sales=non_taxable_sales,
            input_tax_taxable_only=input_tax_taxable_only,
            input_tax_common=input_tax_common,
            input_tax_nontaxable_only=input_tax_nontaxable_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "taxable_ratio": result.taxable_ratio,
        "full_deduction": result.full_deduction,
        "input_tax_total": result.input_tax_total,
        "individual_method_credit": result.individual_method_credit,
        "proportional_method_credit": result.proportional_method_credit,
    }


@router.post("/sales-return-tax")
async def post_sales_return_tax(
    payload: SalesReturnTaxRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> SalesReturnTaxResponse:
    try:
        result = SalesReturnTaxService.compute(
            [
                SalesReturnLine(amount=line.amount, tax_rate=line.tax_rate)
                for line in payload.returns
            ]
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SalesReturnTaxResponse.model_validate(result)


@router.get("/business-tax")
async def get_business_tax(
    taxable_income: Decimal = Query(..., description="課税所得金額"),  # noqa: B008
    months: int = Query(12, description="事業年度の月数(1〜12)"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal]:
    try:
        result = BusinessTaxService.compute(
            taxable_income=taxable_income,
            months=months,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "rounded_income": result.rounded_income,
        "low_base": result.low_base,
        "middle_base": result.middle_base,
        "high_base": result.high_base,
        "tax_amount": result.tax_amount,
    }


@router.get("/local-corporate-tax")
async def get_local_corporate_tax(
    corporate_tax_amount: Decimal = Query(..., description="基準法人税額(法人税額)"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal]:
    try:
        result = LocalCorporateTaxService.compute(
            corporate_tax_amount=corporate_tax_amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "tax_base": result.tax_base,
        "rate": result.rate,
        "tax_amount": result.tax_amount,
    }


@router.get("/corporate-tax")
async def get_corporate_tax(
    taxable_income: Decimal = Query(..., description="課税所得金額"),  # noqa: B008
    months: int = Query(12, description="事業年度の月数(1〜12)"),  # noqa: B008
    small_business: bool = Query(True, description="中小法人(資本金1億円以下等)か"),  # noqa: B008
    excluded_business: bool = Query(False, description="適用除外事業者か"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal]:
    try:
        result = CorporateTaxService.compute(
            taxable_income=taxable_income,
            months=months,
            small_business=small_business,
            excluded_business=excluded_business,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "rounded_income": result.rounded_income,
        "reduced_rate": result.reduced_rate,
        "reduced_bracket": result.reduced_bracket,
        "reduced_tax": result.reduced_tax,
        "standard_tax": result.standard_tax,
        "total_tax": result.total_tax,
    }


@router.get("/bad-debt-consumption-tax")
async def get_bad_debt_consumption_tax(
    bad_debt_amount: Decimal = Query(..., description="貸倒れとなった税込金額"),  # noqa: B008
    tax_rate: Decimal = Query(Decimal("0.10"), description="適用税率(0.10 標準 / 0.08 軽減)"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal]:
    try:
        result = BadDebtConsumptionTaxService.compute(
            bad_debt_amount=bad_debt_amount,
            tax_rate=tax_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "bad_debt_amount": result.bad_debt_amount,
        "tax_rate": result.tax_rate,
        "taxable_base": result.taxable_base,
        "deductible_tax": result.deductible_tax,
    }


@router.get("/bad-debt-reserve")
async def get_bad_debt_reserve(
    receivables: Decimal = Query(..., description="期末一括評価金銭債権の帳簿価額"),  # noqa: B008
    industry: str = Query(..., description="業種(wholesale_retail/manufacturing/finance_insurance/installment_retail/other)"),  # noqa: B008
    non_receivable_amount: Decimal = Query(Decimal("0"), description="実質的に債権とみられない金額"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal]:
    try:
        result = BadDebtReserveService.compute(
            receivables=receivables,
            industry=industry,
            non_receivable_amount=non_receivable_amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "statutory_rate": result.statutory_rate,
        "base_amount": result.base_amount,
        "reserve_limit": result.reserve_limit,
    }


def _to_debtor_receivables(items: list[DebtorReceivableSchema]) -> list[DebtorReceivable]:
    return [
        DebtorReceivable(
            receivable_id=item.receivable_id,
            customer_code=item.customer_code,
            customer_name=item.customer_name,
            amount=item.amount,
            due_date=item.due_date,
            event=item.event,
            event_date=item.event_date,
            secured_amount=item.secured_amount,
            offsettable_amount=item.offsettable_amount,
            written_off_amount=item.written_off_amount,
            repayment_within_5years=item.repayment_within_5years,
            unrecoverable=item.unrecoverable,
            is_trade_receivable=item.is_trade_receivable,
            last_transaction_date=item.last_transaction_date,
        )
        for item in items
    ]


@router.post("/bad-debt-assessment", response_model=BadDebtAssessmentResponse)
async def assess_bad_debts(
    payload: BadDebtAssessmentRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> BadDebtAssessmentResponse:
    """滞留債権を貸倒損失・個別評価・一括評価に振り分け、繰入限度額を算定する。"""
    try:
        result = BadDebtAssessmentService.assess(
            as_of=payload.as_of,
            receivables=_to_debtor_receivables(payload.receivables),
            industry=payload.industry,
            statutory_rate=payload.statutory_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BadDebtAssessmentResponse.model_validate(result)


@router.post("/bad-debt-journal-drafts", response_model=BadDebtJournalResponse)
async def generate_bad_debt_journal_drafts(
    payload: BadDebtJournalRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),  # noqa: B008
) -> BadDebtJournalResponse:
    """貸倒判定の結果から貸倒仕訳ドラフトと引当金の繰入・戻入仕訳を生成する。"""
    try:
        assessment = BadDebtAssessmentService.assess(
            as_of=payload.as_of,
            receivables=_to_debtor_receivables(payload.receivables),
            industry=payload.industry,
            statutory_rate=payload.statutory_rate,
        )
        result = BadDebtJournalDraftService.generate(
            assessment,
            transaction_date=payload.transaction_date,
            allowance_balance=payload.allowance_balance,
            tax_rates=payload.tax_rates,
            tax_treatment=payload.tax_treatment,
            allowance_method=payload.allowance_method,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BadDebtJournalResponse.model_validate(result)


@router.get("/taxable-enterprise")
async def get_taxable_enterprise(
    base_period_taxable_sales: Decimal = Query(..., description="基準期間の課税売上高"),  # noqa: B008
    specific_period_taxable_sales: Decimal = Query(..., description="特定期間の課税売上高"),  # noqa: B008
    specific_period_salaries: Decimal = Query(..., description="特定期間の給与等支払額"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal | bool | str]:
    try:
        result = TaxableEnterpriseJudgmentService.judge(
            base_period_taxable_sales,
            specific_period_taxable_sales,
            specific_period_salaries,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "is_taxable": result.is_taxable,
        "basis": result.basis,
        "base_period_taxable_sales": result.base_period_taxable_sales,
        "specific_period_taxable_sales": result.specific_period_taxable_sales,
        "specific_period_salaries": result.specific_period_salaries,
    }


@router.get("/transitional-deduction")
async def get_invoice_transitional_deduction(
    purchase_consumption_tax: Decimal = Query(..., description="仕入れに係る消費税額"),  # noqa: B008
    transaction_date: date = Query(..., description="取引日"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal | date]:
    try:
        result = InvoiceTransitionalDeductionService.compute(purchase_consumption_tax, transaction_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "transaction_date": result.transaction_date,
        "deduction_rate": result.deduction_rate,
        "deductible_tax": result.deductible_tax,
        "non_deductible_tax": result.non_deductible_tax,
    }


@router.get("/entertainment-deduction")
async def get_entertainment_deduction(
    total_entertainment: Decimal = Query(..., description="交際費等総額"),  # noqa: B008
    dining_expense: Decimal = Query(..., description="飲食費"),  # noqa: B008
    capital: Decimal = Query(..., description="資本金"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal | str]:
    try:
        result = EntertainmentExpenseService.compute(total_entertainment, dining_expense, capital)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "total_entertainment": total_entertainment,
        "dining_expense": dining_expense,
        "capital": capital,
        "deductible_limit": result.deductible_limit,
        "deductible_amount": result.deductible_amount,
        "non_deductible_amount": result.non_deductible_amount,
        "basis": result.basis,
    }
