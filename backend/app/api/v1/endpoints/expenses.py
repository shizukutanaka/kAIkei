from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Employee, ExpenseReport, ExpenseItem
from app.schemas.schemas import (
    ExpenseReportCreate,
    ExpenseReportResponse,
    ExpenseItemResponse,
    ExpenseListResponse,
)
from app.services.auto_journal import generate_expense_payment_journal

router = APIRouter()

VALID_CATEGORIES = {"transport", "meal", "accommodation", "supplies", "entertainment", "other"}
VALID_EXPENSE_TRANSITIONS: dict[str, set[str]] = {
    "submitted": {"approved", "rejected"},
    "approved": {"paid"},
    "rejected": set(),
    "paid": set(),
}


def _to_response(rep: ExpenseReport, emp_name: str | None = None) -> ExpenseReportResponse:
    return ExpenseReportResponse(
        report_id=rep.report_id,
        employee_id=rep.employee_id,
        company_id=rep.company_id,
        report_date=rep.report_date,
        title=rep.title,
        total_amount=rep.total_amount,
        status=rep.status,
        approved_by=rep.approved_by,
        approved_at=rep.approved_at,
        note=rep.note,
        employee_name=emp_name,
        items=[
            ExpenseItemResponse(
                item_id=item.item_id,
                expense_date=item.expense_date,
                category=item.category,
                description=item.description,
                amount=item.amount,
            )
            for item in rep.items
        ],
    )


@router.post("/reports", response_model=ExpenseReportResponse, status_code=201)
async def create_expense_report(
    payload: ExpenseReportCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> ExpenseReportResponse:
    """経費精算を提出する。"""
    if not payload.items:
        raise HTTPException(status_code=422, detail="明細が空です")

    for item in payload.items:
        if item.category not in VALID_CATEGORIES:
            raise HTTPException(
                status_code=422,
                detail=f"無効なカテゴリ: {item.category}。有効な値: {', '.join(sorted(VALID_CATEGORIES))}",
            )

    total = sum(item.amount for item in payload.items)

    rep = ExpenseReport(
        employee_id=payload.employee_id,
        company_id=payload.company_id,
        report_date=payload.report_date,
        title=payload.title,
        total_amount=total,
        status="submitted",
        note=payload.note,
    )
    db.add(rep)
    await db.flush()

    for item in payload.items:
        db.add(ExpenseItem(
            report_id=rep.report_id,
            expense_date=item.expense_date,
            category=item.category,
            description=item.description,
            amount=item.amount,
        ))

    await db.commit()
    await db.refresh(rep, attribute_names=["items"])

    return _to_response(rep)


@router.get("/reports", response_model=ExpenseListResponse)
async def list_expense_reports(
    company_id: UUID = Query(...),
    employee_id: UUID | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> ExpenseListResponse:
    """経費精算一覧を取得する（ページネーション対応）。"""
    base_query = (
        select(ExpenseReport, Employee.employee_name)
        .join(Employee, ExpenseReport.employee_id == Employee.employee_id)
        .where(ExpenseReport.company_id == company_id)
        .options(selectinload(ExpenseReport.items))
    )
    if employee_id:
        base_query = base_query.where(ExpenseReport.employee_id == employee_id)
    if status:
        base_query = base_query.where(ExpenseReport.status == status)

    # Count total
    count_query = (
        select(func.count())
        .select_from(ExpenseReport)
        .where(ExpenseReport.company_id == company_id)
    )
    if employee_id:
        count_query = count_query.where(ExpenseReport.employee_id == employee_id)
    if status:
        count_query = count_query.where(ExpenseReport.status == status)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginated query
    query = base_query.order_by(ExpenseReport.report_date.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.all()
    items = [_to_response(rep, name) for rep, name in rows]

    return ExpenseListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/reports/{report_id}", response_model=ExpenseReportResponse)
async def get_expense_report(
    report_id: UUID,
    company_id: UUID = Query(..., description="会社ID（テナント検証用）"),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> ExpenseReportResponse:
    """経費精算詳細を取得する。"""
    result = await db.execute(
        select(ExpenseReport, Employee.employee_name)
        .join(Employee, ExpenseReport.employee_id == Employee.employee_id)
        .where(ExpenseReport.report_id == report_id, ExpenseReport.company_id == company_id)
        .options(selectinload(ExpenseReport.items))
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="経費精算が見つかりません")
    rep, name = row
    return _to_response(rep, name)


@router.post("/reports/{report_id}/transition", response_model=ExpenseReportResponse)
async def transition_expense_report(
    report_id: UUID,
    action: str = Query(..., description="approved, rejected, paid"),
    company_id: UUID = Query(..., description="会社ID（テナント検証用）"),
    current_user: CurrentUser = Depends(require_permission(Permission.PAYROLL_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> ExpenseReportResponse:
    """経費精算のステータスを変更する。"""
    result = await db.execute(
        select(ExpenseReport, Employee.employee_name)
        .join(Employee, ExpenseReport.employee_id == Employee.employee_id)
        .where(ExpenseReport.report_id == report_id, ExpenseReport.company_id == company_id)
        .options(selectinload(ExpenseReport.items))
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="経費精算が見つかりません")

    rep, name = row
    allowed = VALID_EXPENSE_TRANSITIONS.get(rep.status, set())
    if action not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"現在のステータス「{rep.status}」から「{action}」への遷移は許可されていません",
        )

    rep.status = action
    if action == "approved":
        rep.approved_by = current_user.user_id
        rep.approved_at = datetime.now()
    elif action == "paid":
        try:
            await generate_expense_payment_journal(
                db,
                company_id=rep.company_id,
                report_title=rep.title,
                payment_date=rep.report_date,
                total_amount=rep.total_amount,
                created_by=current_user.user_id,
            )
        except ValueError:
            pass  # Account not found — skip auto-journal

    await db.commit()
    await db.refresh(rep, attribute_names=["items"])
    return _to_response(rep, name)


@router.get("/reports/{report_id}/export", response_class=PlainTextResponse)
async def export_expense_report(
    report_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> str:
    """経費精算をCSV形式で出力する。"""
    result = await db.execute(
        select(ExpenseReport, Employee.employee_name, Employee.employee_code, Employee.department)
        .join(Employee, ExpenseReport.employee_id == Employee.employee_id)
        .where(ExpenseReport.report_id == report_id)
        .options(selectinload(ExpenseReport.items))
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="経費精算が見つかりません")

    rep, emp_name, emp_code, dept = row

    category_labels = {
        "transport": "交通費",
        "meal": "会議費",
        "accommodation": "宿泊費",
        "supplies": "備品消耗品",
        "entertainment": "接待交際費",
        "other": "その他",
    }

    lines = [
        "項目,内容",
        f"従業員コード,{emp_code}",
        f"従業員名,{emp_name}",
        f"部署,{dept or ''}",
        f"精算日,{rep.report_date}",
        f"タイトル,{rep.title}",
        f"ステータス,{rep.status}",
        f"合計金額,{rep.total_amount}",
        "",
        "日付,カテゴリ,摘要,金額",
    ]

    for item in rep.items:
        cat_label = category_labels.get(item.category, item.category)
        lines.append(f"{item.expense_date},{cat_label},{item.description},{item.amount}")

    lines.append("")
    lines.append(f"合計,{rep.total_amount}")

    return "\n".join(lines)
