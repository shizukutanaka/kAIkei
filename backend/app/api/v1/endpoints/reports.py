from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, case
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
    # Single aggregate query: GROUP BY account, SUM debits/credits
    agg_result = await db.execute(
        select(
            Account.account_id,
            Account.account_code,
            Account.account_name,
            Account.account_type,
            Account.debit_credit,
            func.coalesce(
                func.sum(
                    case(
                        (JournalLine.debit_credit == "debit", JournalLine.amount),
                        else_=Decimal("0"),
                    )
                ), 0
            ).label("debit_sum"),
            func.coalesce(
                func.sum(
                    case(
                        (JournalLine.debit_credit == "credit", JournalLine.amount),
                        else_=Decimal("0"),
                    )
                ), 0
            ).label("credit_sum"),
        )
        .outerjoin(
            JournalLine,
            (JournalLine.account_id == Account.account_id) & (JournalLine.is_deleted == False),  # noqa: E712
        )
        .outerjoin(
            JournalHeader,
            (JournalHeader.journal_header_id == JournalLine.journal_header_id)
            & (JournalHeader.company_id == company_id)
            & (JournalHeader.transaction_date <= as_of)
            & (JournalHeader.is_deleted == False)  # noqa: E712
            & (JournalHeader.is_voided == False),  # noqa: E712
        )
        .where(
            Account.company_id == company_id,
            Account.is_deleted == False,  # noqa: E712
            Account.is_active == True,  # noqa: E712
        )
        .group_by(
            Account.account_id,
            Account.account_code,
            Account.account_name,
            Account.account_type,
            Account.debit_credit,
        )
        .order_by(Account.account_code)
    )
    rows = agg_result.all()

    balances: list[dict] = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")

    for row in rows:
        debit_sum = Decimal(row.debit_sum) if row.debit_sum else Decimal("0")
        credit_sum = Decimal(row.credit_sum) if row.credit_sum else Decimal("0")
        balance = debit_sum - credit_sum

        if row.debit_credit == "debit":
            display_debit = balance if balance > 0 else Decimal("0")
            display_credit = -balance if balance < 0 else Decimal("0")
        else:
            display_credit = -balance if balance < 0 else Decimal("0")
            display_debit = balance if balance > 0 else Decimal("0")

        total_debit += display_debit
        total_credit += display_credit

        balances.append({
            "account_code": row.account_code,
            "account_name": row.account_name,
            "account_type": row.account_type,
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


# Account types for P/L and B/S
PL_ACCOUNT_TYPES = {"revenue", "expense"}
BS_ACCOUNT_TYPES = {"asset", "liability", "equity"}


async def _get_account_balances(
    db: AsyncSession,
    company_id: UUID,
    as_of: date,
    account_types: set[str],
) -> list[tuple]:
    """Get aggregated balances for accounts of given types."""
    result = await db.execute(
        select(
            Account.account_code,
            Account.account_name,
            Account.account_type,
            Account.debit_credit,
            func.coalesce(
                func.sum(
                    case(
                        (JournalLine.debit_credit == "debit", JournalLine.amount),
                        else_=Decimal("0"),
                    )
                ), 0
            ).label("debit_sum"),
            func.coalesce(
                func.sum(
                    case(
                        (JournalLine.debit_credit == "credit", JournalLine.amount),
                        else_=Decimal("0"),
                    )
                ), 0
            ).label("credit_sum"),
        )
        .outerjoin(
            JournalLine,
            (JournalLine.account_id == Account.account_id) & (JournalLine.is_deleted == False),  # noqa: E712
        )
        .outerjoin(
            JournalHeader,
            (JournalHeader.journal_header_id == JournalLine.journal_header_id)
            & (JournalHeader.company_id == company_id)
            & (JournalHeader.transaction_date <= as_of)
            & (JournalHeader.is_deleted == False)  # noqa: E712
            & (JournalHeader.is_voided == False),  # noqa: E712
        )
        .where(
            Account.company_id == company_id,
            Account.is_deleted == False,  # noqa: E712
            Account.is_active == True,  # noqa: E712
            Account.account_type.in_(account_types),
        )
        .group_by(
            Account.account_id,
            Account.account_code,
            Account.account_name,
            Account.account_type,
            Account.debit_credit,
        )
        .order_by(Account.account_code)
    )
    return result.all()


@router.get("/income-statement")
async def get_income_statement(
    company_id: UUID,
    as_of: date = Query(..., description="期末日"),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """損益計算書（P/L）を取得する。

    収益 - 費用 = 当期純利益
    """
    rows = await _get_account_balances(db, company_id, as_of, PL_ACCOUNT_TYPES)

    revenues: list[dict] = []
    expenses: list[dict] = []
    total_revenue = Decimal("0")
    total_expense = Decimal("0")

    for row in rows:
        debit_sum = Decimal(row.debit_sum) if row.debit_sum else Decimal("0")
        credit_sum = Decimal(row.credit_sum) if row.credit_sum else Decimal("0")
        balance = debit_sum - credit_sum

        if row.account_type == "revenue":
            # Revenue is credit-normal: credit - debit
            amount = credit_sum - debit_sum
            total_revenue += amount
            revenues.append({
                "account_code": row.account_code,
                "account_name": row.account_name,
                "amount": str(amount),
            })
        elif row.account_type == "expense":
            # Expense is debit-native: debit - credit
            amount = debit_sum - credit_sum
            total_expense += amount
            expenses.append({
                "account_code": row.account_code,
                "account_name": row.account_name,
                "amount": str(amount),
            })

    net_income = total_revenue - total_expense

    return {
        "as_of": as_of.isoformat(),
        "revenues": revenues,
        "total_revenue": str(total_revenue),
        "expenses": expenses,
        "total_expense": str(total_expense),
        "net_income": str(net_income),
    }


@router.get("/balance-sheet")
async def get_balance_sheet(
    company_id: UUID,
    as_of: date = Query(..., description="基準日"),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """貸借対照表（B/S）を取得する。

    資産 = 負債 + 純資産
    """
    rows = await _get_account_balances(db, company_id, as_of, BS_ACCOUNT_TYPES)

    assets: list[dict] = []
    liabilities: list[dict] = []
    equity: list[dict] = []
    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    total_equity = Decimal("0")

    for row in rows:
        debit_sum = Decimal(row.debit_sum) if row.debit_sum else Decimal("0")
        credit_sum = Decimal(row.credit_sum) if row.credit_sum else Decimal("0")
        balance = debit_sum - credit_sum

        entry = {
            "account_code": row.account_code,
            "account_name": row.account_name,
            "amount": str(abs(balance)),
        }

        if row.account_type == "asset":
            amount = debit_sum - credit_sum
            total_assets += amount
            entry["amount"] = str(amount)
            assets.append(entry)
        elif row.account_type == "liability":
            amount = credit_sum - debit_sum
            total_liabilities += amount
            entry["amount"] = str(amount)
            liabilities.append(entry)
        elif row.account_type == "equity":
            amount = credit_sum - debit_sum
            total_equity += amount
            entry["amount"] = str(amount)
            equity.append(entry)

    return {
        "as_of": as_of.isoformat(),
        "assets": assets,
        "total_assets": str(total_assets),
        "liabilities": liabilities,
        "total_liabilities": str(total_liabilities),
        "equity": equity,
        "total_equity": str(total_equity),
        "is_balanced": total_assets == (total_liabilities + total_equity),
    }
