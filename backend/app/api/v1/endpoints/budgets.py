from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Account, Budget, BudgetLine, MonthlyBalance
from app.schemas.schemas import (
    BudgetCreate,
    BudgetResponse,
    BudgetVarianceLine,
    BudgetVarianceResponse,
)
from app.services.budget_service import BudgetService

router = APIRouter()


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget(
    payload: BudgetCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    existing = await db.execute(
        select(Budget).where(
            Budget.company_id == payload.company_id,
            Budget.fiscal_year == payload.fiscal_year,
            Budget.name == payload.name,
            Budget.is_deleted == False,  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Budget already exists for this fiscal year and name")

    budget = Budget(
        company_id=payload.company_id,
        fiscal_year=payload.fiscal_year,
        name=payload.name,
    )
    for line in payload.lines:
        budget.lines.append(
            BudgetLine(
                account_id=line.account_id,
                month=line.month,
                budgeted_amount=line.budgeted_amount,
            )
        )
    db.add(budget)
    await db.flush()
    await db.refresh(budget)
    return BudgetResponse.model_validate(budget)


@router.get("", response_model=list[BudgetResponse])
async def list_budgets(
    company_id: UUID,
    fiscal_year: int | None = None,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[BudgetResponse]:
    stmt = select(Budget).where(
        Budget.company_id == company_id,
        Budget.is_deleted == False,  # noqa: E712
    )
    if fiscal_year is not None:
        stmt = stmt.where(Budget.fiscal_year == fiscal_year)
    stmt = stmt.order_by(Budget.fiscal_year.desc(), Budget.name)
    result = await db.execute(stmt)
    return [BudgetResponse.model_validate(b) for b in result.scalars().unique().all()]


async def _get_budget_or_404(budget_id: UUID, db: AsyncSession) -> Budget:
    result = await db.execute(
        select(Budget).where(Budget.budget_id == budget_id, Budget.is_deleted == False)  # noqa: E712
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.get("/{budget_id}", response_model=BudgetResponse)
async def get_budget(
    budget_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    budget = await _get_budget_or_404(budget_id, db)
    return BudgetResponse.model_validate(budget)


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_DELETE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    budget = await _get_budget_or_404(budget_id, db)
    budget.is_deleted = True
    await db.flush()


@router.get("/{budget_id}/variance", response_model=BudgetVarianceResponse)
async def get_budget_variance(
    budget_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> BudgetVarianceResponse:
    budget = await _get_budget_or_404(budget_id, db)

    budgeted_by_account: dict[UUID, Decimal] = {}
    for line in budget.lines:
        budgeted_by_account[line.account_id] = budgeted_by_account.get(line.account_id, Decimal("0")) + line.budgeted_amount

    accounts_result = await db.execute(
        select(Account).where(Account.company_id == budget.company_id, Account.is_deleted == False)  # noqa: E712
    )
    accounts = {a.account_id: a for a in accounts_result.scalars().all()}

    balances_result = await db.execute(
        select(MonthlyBalance).where(
            MonthlyBalance.company_id == budget.company_id,
            MonthlyBalance.year == budget.fiscal_year,
            MonthlyBalance.is_deleted == False,  # noqa: E712
        )
    )
    actual_by_account: dict[UUID, Decimal] = {}
    for bal in balances_result.scalars().all():
        account = accounts.get(bal.account_id)
        if account is None:
            continue
        actual = BudgetService.actual_from_balance(bal.debit_total, bal.credit_total, account.debit_credit)
        actual_by_account[bal.account_id] = actual_by_account.get(bal.account_id, Decimal("0")) + actual

    variance_lines: list[BudgetVarianceLine] = []
    summary_inputs: list[dict[str, Decimal | bool]] = []
    for account_id, budgeted in sorted(budgeted_by_account.items(), key=lambda kv: accounts[kv[0]].account_code if kv[0] in accounts else ""):
        account = accounts.get(account_id)
        actual = actual_by_account.get(account_id, Decimal("0"))
        variance = BudgetService.line_variance(budgeted, actual)
        summary_inputs.append(variance)
        variance_lines.append(
            BudgetVarianceLine(
                account_id=account_id,
                account_code=account.account_code if account else "",
                account_name=account.account_name if account else "",
                budgeted_amount=budgeted,
                actual_amount=actual,
                variance_amount=Decimal(str(variance["variance_amount"])),
                variance_rate=Decimal(str(variance["variance_rate"])),
                execution_rate=Decimal(str(variance["execution_rate"])),
                is_over_budget=bool(variance["is_over_budget"]),
            )
        )

    summary = BudgetService.summarize(summary_inputs)
    return BudgetVarianceResponse(
        budget_id=budget.budget_id,
        fiscal_year=budget.fiscal_year,
        budgeted_total=Decimal(str(summary["budgeted_total"])),
        actual_total=Decimal(str(summary["actual_total"])),
        variance_total=Decimal(str(summary["variance_total"])),
        execution_rate=Decimal(str(summary["execution_rate"])),
        over_budget_count=int(summary["over_budget_count"]),
        line_count=int(summary["line_count"]),
        lines=variance_lines,
    )
