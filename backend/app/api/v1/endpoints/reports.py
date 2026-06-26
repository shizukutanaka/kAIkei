from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Account, JournalHeader, JournalLine, MonthlyBalance

router = APIRouter()


@router.get("/trial-balance")
async def get_trial_balance(
    company_id: UUID,
    as_of: date = Query(..., description="基準日"),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """試算表（Trial Balance）を取得する。

    全科目の借方合計・貸方合計・残高を返す。
    """
    accounts_result = await db.execute(
        select(Account).where(
            Account.company_id == company_id,
            Account.is_deleted == False,  # noqa: E712
            Account.is_active == True,  # noqa: E712
        ).order_by(Account.account_code)
    )
    accounts = accounts_result.scalars().all()

    balances: list[dict] = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")

    for account in accounts:
        debit_sum = Decimal("0")
        credit_sum = Decimal("0")

        lines_result = await db.execute(
            select(JournalLine).join(JournalHeader).where(
                JournalHeader.company_id == company_id,
                JournalLine.account_id == account.account_id,
                JournalHeader.transaction_date <= as_of,
                JournalHeader.is_deleted == False,  # noqa: E712
                JournalHeader.is_voided == False,  # noqa: E712
                JournalLine.is_deleted == False,  # noqa: E712
            )
        )
        lines = lines_result.scalars().all()

        for line in lines:
            if line.debit_credit == "debit":
                debit_sum += line.amount
            else:
                credit_sum += line.amount

        balance = debit_sum - credit_sum

        if account.debit_credit == "debit":
            display_debit = balance if balance > 0 else Decimal("0")
            display_credit = -balance if balance < 0 else Decimal("0")
        else:
            display_credit = -balance if balance < 0 else Decimal("0")
            display_debit = balance if balance > 0 else Decimal("0")

        total_debit += display_debit
        total_credit += display_credit

        balances.append({
            "account_code": account.account_code,
            "account_name": account.account_name,
            "account_type": account.account_type,
            "debit_total": str(debit_sum),
            "credit_total": str(credit_sum),
            "balance": str(balance),
            "display_debit": str(display_debit),
            "display_credit": str(display_credit),
        })

    return {
        "as_of": as_of.isoformat(),
        "accounts": balances,
        "total_debit": str(total_debit),
        "total_credit": str(total_credit),
        "is_balanced": total_debit == total_credit,
    }


@router.get("/monthly-balances")
async def get_monthly_balances(
    company_id: UUID,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """月次残高を取得する。"""
    result = await db.execute(
        select(MonthlyBalance, Account).join(Account).where(
            MonthlyBalance.company_id == company_id,
            MonthlyBalance.year == year,
            MonthlyBalance.month == month,
            MonthlyBalance.is_deleted == False,  # noqa: E712
        ).order_by(Account.account_code)
    )
    rows = result.all()

    items = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")

    for balance, account in rows:
        total_debit += balance.debit_total
        total_credit += balance.credit_total
        items.append({
            "account_code": account.account_code,
            "account_name": account.account_name,
            "debit_total": str(balance.debit_total),
            "credit_total": str(balance.credit_total),
            "balance": str(balance.debit_total - balance.credit_total),
        })

    return {
        "year": year,
        "month": month,
        "items": items,
        "total_debit": str(total_debit),
        "total_credit": str(total_credit),
        "is_balanced": total_debit == total_credit,
    }
