from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Account, JournalHeader, JournalLine, MonthlyBalance, PeriodClose

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


# ---------------------------------------------------------------------------
# Cash Flow Statement (キャッシュフロー計算書)
# ---------------------------------------------------------------------------

@router.get("/cash-flow")
async def get_cash_flow_statement(
    company_id: UUID,
    as_of: date = Query(..., description="期末日"),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """キャッシュフロー計算書を取得する（簡易版・間接法）。

    営業CF = 当期純利益 + 減価償却 - 売上債権増減 + 買掛債務増減
    投資CF = 固定資産取得・除却
    財務CF = 借入・返済・配当
    """
    # Get P/L data
    pl_rows = await _get_account_balances(db, company_id, as_of, {"revenue", "expense"})
    total_revenue = Decimal("0")
    total_expense = Decimal("0")
    for row in pl_rows:
        ds = Decimal(row.debit_sum) if row.debit_sum else Decimal("0")
        cs = Decimal(row.credit_sum) if row.credit_sum else Decimal("0")
        if row.account_type == "revenue":
            total_revenue += cs - ds
        elif row.account_type == "expense":
            total_expense += ds - cs
    net_income = total_revenue - total_expense

    # Get B/S data for working capital changes
    bs_rows = await _get_account_balances(db, company_id, as_of, BS_ACCOUNT_TYPES)

    operating_items: list[dict] = []
    investing_items: list[dict] = []
    financing_items: list[dict] = []

    # Operating CF: indirect method
    operating_items.append({"item": "当期純利益", "amount": str(net_income)})

    # Classify accounts into CF categories
    operating_total = net_income
    investing_total = Decimal("0")
    financing_total = Decimal("0")

    for row in bs_rows:
        ds = Decimal(row.debit_sum) if row.debit_sum else Decimal("0")
        cs = Decimal(row.credit_sum) if row.credit_sum else Decimal("0")

        if row.account_type == "asset":
            code = row.account_code or ""
            if code.startswith("11"):  # Accounts receivable
                change = ds - cs
                operating_items.append({"item": f"売上債権増減 ({row.account_name})", "amount": str(-change)})
                operating_total -= change
            elif code.startswith("10"):  # Cash — skip, this is the target
                pass
            elif code.startswith("17"):  # Accumulated depreciation
                dep = cs - ds
                operating_items.append({"item": f"減価償却 ({row.account_name})", "amount": str(dep)})
                operating_total += dep
            elif code.startswith("1"):  # Other assets = investing
                change = ds - cs
                investing_items.append({"item": f"固定資産等増減 ({row.account_name})", "amount": str(-change)})
                investing_total -= change
        elif row.account_type == "liability":
            code = row.account_code or ""
            if code.startswith("20") or code.startswith("21"):  # Accounts payable / tax
                change = cs - ds
                operating_items.append({"item": f"買掛債務等増減 ({row.account_name})", "amount": str(change)})
                operating_total += change
            elif code.startswith("2"):  # Other liabilities = financing
                change = cs - ds
                financing_items.append({"item": f"借入金等増減 ({row.account_name})", "amount": str(change)})
                financing_total += change
        elif row.account_type == "equity":
            change = cs - ds
            if change != 0:
                financing_items.append({"item": f"資本増減 ({row.account_name})", "amount": str(change)})
                financing_total += change

    net_cf = operating_total + investing_total + financing_total

    return {
        "as_of": str(as_of),
        "operating": {
            "items": operating_items,
            "subtotal": str(operating_total),
        },
        "investing": {
            "items": investing_items,
            "subtotal": str(investing_total),
        },
        "financing": {
            "items": financing_items,
            "subtotal": str(financing_total),
        },
        "net_cash_flow": str(net_cf),
    }


# ---------------------------------------------------------------------------
# CSV export endpoints
# ---------------------------------------------------------------------------

@router.get("/trial-balance/export", response_class=PlainTextResponse)
async def export_trial_balance_csv(
    company_id: UUID,
    as_of: date = Query(..., description="基準日"),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> str:
    """試算表をCSV形式で出力する。"""
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
        )
        .group_by(Account.account_id, Account.account_code, Account.account_name, Account.account_type, Account.debit_credit)
        .order_by(Account.account_code)
    )
    rows = result.all()

    lines = ["科目コード,科目名,区分,借方合計,貸方合計,残高"]
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for row in rows:
        ds = Decimal(row.debit_sum) if row.debit_sum else Decimal("0")
        cs = Decimal(row.credit_sum) if row.credit_sum else Decimal("0")
        bal = ds - cs
        total_debit += ds
        total_credit += cs
        lines.append(f"{row.account_code},{row.account_name},{row.account_type},{ds},{cs},{bal}")
    lines.append(f",合計,,{total_debit},{total_credit},{total_debit - total_credit}")
    return "\n".join(lines)


@router.get("/income-statement/export", response_class=PlainTextResponse)
async def export_income_statement_csv(
    company_id: UUID,
    as_of: date = Query(..., description="期末日"),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> str:
    """損益計算書をCSV形式で出力する。"""
    rows = await _get_account_balances(db, company_id, as_of, PL_ACCOUNT_TYPES)

    lines = ["区分,科目コード,科目名,金額"]
    total_rev = Decimal("0")
    total_exp = Decimal("0")
    for row in rows:
        ds = Decimal(row.debit_sum) if row.debit_sum else Decimal("0")
        cs = Decimal(row.credit_sum) if row.credit_sum else Decimal("0")
        if row.account_type == "revenue":
            amt = cs - ds
            total_rev += amt
            lines.append(f"収益,{row.account_code},{row.account_name},{amt}")
        elif row.account_type == "expense":
            amt = ds - cs
            total_exp += amt
            lines.append(f"費用,{row.account_code},{row.account_name},{amt}")
    lines.append(f",,収益合計,{total_rev}")
    lines.append(f",,費用合計,{total_exp}")
    lines.append(f",,当期純利益,{total_rev - total_exp}")
    return "\n".join(lines)


@router.get("/balance-sheet/export", response_class=PlainTextResponse)
async def export_balance_sheet_csv(
    company_id: UUID,
    as_of: date = Query(..., description="基準日"),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> str:
    """貸借対照表をCSV形式で出力する。"""
    rows = await _get_account_balances(db, company_id, as_of, BS_ACCOUNT_TYPES)

    lines = ["区分,科目コード,科目名,金額"]
    total_a = Decimal("0")
    total_l = Decimal("0")
    total_e = Decimal("0")
    for row in rows:
        ds = Decimal(row.debit_sum) if row.debit_sum else Decimal("0")
        cs = Decimal(row.credit_sum) if row.credit_sum else Decimal("0")
        if row.account_type == "asset":
            amt = ds - cs
            total_a += amt
            lines.append(f"資産,{row.account_code},{row.account_name},{amt}")
        elif row.account_type == "liability":
            amt = cs - ds
            total_l += amt
            lines.append(f"負債,{row.account_code},{row.account_name},{amt}")
        elif row.account_type == "equity":
            amt = cs - ds
            total_e += amt
            lines.append(f"純資産,{row.account_code},{row.account_name},{amt}")
    lines.append(f",,資産合計,{total_a}")
    lines.append(f",,負債合計,{total_l}")
    lines.append(f",,純資産合計,{total_e}")
    lines.append(f",,負債純資産合計,{total_l + total_e}")
    return "\n".join(lines)


@router.get("/cash-flow/export", response_class=PlainTextResponse)
async def export_cash_flow_csv(
    company_id: UUID,
    as_of: date = Query(..., description="期末日"),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> str:
    """キャッシュフロー計算書をCSV形式で出力する。"""
    # Reuse the cash flow logic
    pl_rows = await _get_account_balances(db, company_id, as_of, {"revenue", "expense"})
    total_revenue = Decimal("0")
    total_expense = Decimal("0")
    for row in pl_rows:
        ds = Decimal(row.debit_sum) if row.debit_sum else Decimal("0")
        cs = Decimal(row.credit_sum) if row.credit_sum else Decimal("0")
        if row.account_type == "revenue":
            total_revenue += cs - ds
        elif row.account_type == "expense":
            total_expense += ds - cs
    net_income = total_revenue - total_expense

    bs_rows = await _get_account_balances(db, company_id, as_of, BS_ACCOUNT_TYPES)

    lines = ["区分,項目,金額"]
    operating_total = net_income
    investing_total = Decimal("0")
    financing_total = Decimal("0")

    lines.append(f"営業CF,当期純利益,{net_income}")

    for row in bs_rows:
        ds = Decimal(row.debit_sum) if row.debit_sum else Decimal("0")
        cs = Decimal(row.credit_sum) if row.credit_sum else Decimal("0")
        code = row.account_code or ""

        if row.account_type == "asset":
            if code.startswith("11"):
                change = ds - cs
                lines.append(f"営業CF,売上債権増減 ({row.account_name}),{-change}")
                operating_total -= change
            elif code.startswith("10"):
                pass
            elif code.startswith("17"):
                dep = cs - ds
                lines.append(f"営業CF,減価償却 ({row.account_name}),{dep}")
                operating_total += dep
            elif code.startswith("1"):
                change = ds - cs
                lines.append(f"投資CF,固定資産等増減 ({row.account_name}),{-change}")
                investing_total -= change
        elif row.account_type == "liability":
            if code.startswith("20") or code.startswith("21"):
                change = cs - ds
                lines.append(f"営業CF,買掛債務等増減 ({row.account_name}),{change}")
                operating_total += change
            elif code.startswith("2"):
                change = cs - ds
                lines.append(f"財務CF,借入金等増減 ({row.account_name}),{change}")
                financing_total += change
        elif row.account_type == "equity":
            change = cs - ds
            if change != 0:
                lines.append(f"財務CF,資本増減 ({row.account_name}),{change}")
                financing_total += change

    lines.append(f",営業CF小計,{operating_total}")
    lines.append(f",投資CF小計,{investing_total}")
    lines.append(f",財務CF小計,{financing_total}")
    lines.append(f",現金純増減,{operating_total + investing_total + financing_total}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Period close (月次締切)
# ---------------------------------------------------------------------------

VALID_CLOSE_ACTIONS = {"close", "reopen"}


@router.get("/period-closes")
async def list_period_closes(
    company_id: UUID = Query(...),
    year: int = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """指定期間の月次締切状態を取得する。"""
    result = await db.execute(
        select(PeriodClose).where(
            PeriodClose.company_id == company_id,
            PeriodClose.year == year,
        ).order_by(PeriodClose.month)
    )
    rows = result.scalars().all()
    return [
        {
            "close_id": str(r.close_id),
            "company_id": str(r.company_id),
            "year": r.year,
            "month": r.month,
            "status": r.status,
            "closed_by": str(r.closed_by) if r.closed_by else None,
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
            "note": r.note,
        }
        for r in rows
    ]


@router.post("/period-closes")
async def transition_period_close(
    company_id: UUID = Query(...),
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    action: str = Query(..., description="close or reopen"),
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """月次締切状態を変更する（close / reopen）。"""
    if action not in VALID_CLOSE_ACTIONS:
        raise HTTPException(status_code=400, detail=f"action は {VALID_CLOSE_ACTIONS} のいずれかです")

    result = await db.execute(
        select(PeriodClose).where(
            PeriodClose.company_id == company_id,
            PeriodClose.year == year,
            PeriodClose.month == month,
        )
    )
    record = result.scalar_one_or_none()

    if not record:
        record = PeriodClose(
            company_id=company_id,
            year=year,
            month=month,
            status="open",
        )
        db.add(record)
        await db.flush()

    if action == "close":
        if record.status == "closed":
            raise HTTPException(status_code=409, detail=f"{year}年{month}月は既に締切済みです")
        record.status = "closed"
        record.closed_by = current_user.user_id
        record.closed_at = datetime.utcnow()
    else:  # reopen
        if record.status != "closed":
            raise HTTPException(status_code=409, detail=f"{year}年{month}月は締切済みではありません")
        record.status = "open"
        record.closed_by = None
        record.closed_at = None

    await db.commit()
    await db.refresh(record)
    return {
        "close_id": str(record.close_id),
        "company_id": str(record.company_id),
        "year": record.year,
        "month": record.month,
        "status": record.status,
        "closed_by": str(record.closed_by) if record.closed_by else None,
        "closed_at": record.closed_at.isoformat() if record.closed_at else None,
    }
