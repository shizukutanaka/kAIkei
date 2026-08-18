from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import delete, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csv_export import csv_line
from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission, verified_company_id
from app.core.rbac import Permission
from app.core.tenant_scope import assert_company_access, scope_to_tenant
from app.models.models import Account, JournalHeader, JournalLine, TaxReturn
from app.schemas.schemas import TaxReturnCalculateRequest, TaxReturnListResponse, TaxReturnResponse

router = APIRouter()

TAX_RATE = Decimal("10")  # 10% (軽減税率8%は複雑なので簡略化)
VALID_FILING_TYPES = {"general", "simplified"}
VALID_TRANSITIONS: dict[str, set[str]] = {
    "calculated": {"filed"},
    "filed": set(),
}


def _round(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _to_response(tr: TaxReturn) -> TaxReturnResponse:
    return TaxReturnResponse(
        return_id=tr.return_id,
        company_id=tr.company_id,
        tax_year=tr.tax_year,
        filing_type=tr.filing_type,
        taxable_sales=tr.taxable_sales,
        non_taxable_sales=tr.non_taxable_sales,
        export_taxable_sales=tr.export_taxable_sales,
        total_sales=tr.total_sales,
        purchases_subject_to_tax=tr.purchases_subject_to_tax,
        purchases_not_subject_to_tax=tr.purchases_not_subject_to_tax,
        total_purchases=tr.total_purchases,
        output_tax=tr.output_tax,
        input_tax=tr.input_tax,
        tax_adjustment=tr.tax_adjustment,
        tax_payable=tr.tax_payable,
        status=tr.status,
        note=tr.note,
    )


@router.post("/calculate", response_model=TaxReturnResponse, status_code=201)
async def calculate_tax_return(
    payload: TaxReturnCalculateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> TaxReturnResponse:
    """消費税申告を計算する（仕訳データから集計）。"""
    await assert_company_access(db, current_user, payload.company_id)
    if payload.filing_type not in VALID_FILING_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"無効な申告区分: {payload.filing_type}。有効な値: general, simplified",
        )

    # Delete existing for same company/year
    await db.execute(
        delete(TaxReturn).where(
            TaxReturn.company_id == payload.company_id,
            TaxReturn.tax_year == payload.tax_year,
        )
    )

    # Aggregate journal lines by account type for the given year
    # Revenue accounts -> sales, Expense accounts -> purchases
    revenue_lines = await db.execute(
        select(
            func.coalesce(func.sum(JournalLine.amount), 0).label("total"),
        )
        .join(JournalHeader, JournalLine.journal_header_id == JournalHeader.journal_header_id)
        .join(Account, JournalLine.account_id == Account.account_id)
        .where(
            JournalHeader.company_id == payload.company_id,
            extract("year", JournalHeader.transaction_date) == payload.tax_year,
            Account.account_type == "revenue",
            JournalLine.debit_credit == "credit",
            JournalHeader.approval_status.in_(["approved", "posted"]),
        )
    )
    total_revenue = revenue_lines.scalar() or Decimal("0")

    expense_lines = await db.execute(
        select(
            func.coalesce(func.sum(JournalLine.amount), 0).label("total"),
        )
        .join(JournalHeader, JournalLine.journal_header_id == JournalHeader.journal_header_id)
        .join(Account, JournalLine.account_id == Account.account_id)
        .where(
            JournalHeader.company_id == payload.company_id,
            extract("year", JournalHeader.transaction_date) == payload.tax_year,
            Account.account_type == "expense",
            JournalLine.debit_credit == "debit",
            JournalHeader.approval_status.in_(["approved", "posted"]),
        )
    )
    total_expense = expense_lines.scalar() or Decimal("0")

    # Simplified: assume 80% of revenue is taxable, 20% non-taxable
    # In production, this would come from tax classification per journal line
    taxable_sales = _round(total_revenue * Decimal("0.8"))
    non_taxable_sales = _round(total_revenue * Decimal("0.2"))
    export_taxable_sales = Decimal("0")
    total_sales = taxable_sales + non_taxable_sales + export_taxable_sales

    if payload.filing_type == "simplified":
        # 簡易課税: みなし仕入率（小売50%, 卸売60%, 製造70%, 飲食80%, その他90%）
        # Default to 90% (その他)
        deemed_purchase_rate = Decimal("0.90")
        purchases_subject_to_tax = _round(taxable_sales * deemed_purchase_rate)
        purchases_not_subject_to_tax = _round(total_expense - purchases_subject_to_tax)
    else:
        # 一般課税: actual purchases
        purchases_subject_to_tax = _round(total_expense * Decimal("0.8"))
        purchases_not_subject_to_tax = _round(total_expense * Decimal("0.2"))

    total_purchases = purchases_subject_to_tax + purchases_not_subject_to_tax

    output_tax = _round(taxable_sales * TAX_RATE / Decimal("100"))
    input_tax = _round(purchases_subject_to_tax * TAX_RATE / Decimal("100"))
    tax_payable = output_tax - input_tax + payload.tax_adjustment

    tr = TaxReturn(
        company_id=payload.company_id,
        tax_year=payload.tax_year,
        filing_type=payload.filing_type,
        taxable_sales=taxable_sales,
        non_taxable_sales=non_taxable_sales,
        export_taxable_sales=export_taxable_sales,
        total_sales=total_sales,
        purchases_subject_to_tax=purchases_subject_to_tax,
        purchases_not_subject_to_tax=purchases_not_subject_to_tax,
        total_purchases=total_purchases,
        output_tax=output_tax,
        input_tax=input_tax,
        tax_adjustment=payload.tax_adjustment,
        tax_payable=tax_payable,
        status="calculated",
    )
    db.add(tr)
    await db.commit()
    await db.refresh(tr)
    return _to_response(tr)


@router.get("/records", response_model=TaxReturnListResponse)
async def list_tax_returns(
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> TaxReturnListResponse:
    """消費税申告一覧を取得する。"""
    count_result = await db.execute(
        select(func.count()).select_from(TaxReturn).where(TaxReturn.company_id == company_id)
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(TaxReturn)
        .where(TaxReturn.company_id == company_id)
        .order_by(TaxReturn.tax_year.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_to_response(tr) for tr in result.scalars().all()]
    return TaxReturnListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/records/{return_id}", response_model=TaxReturnResponse)
async def get_tax_return(
    return_id: UUID,
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> TaxReturnResponse:
    """消費税申告詳細を取得する。"""
    result = await db.execute(select(TaxReturn).where(TaxReturn.return_id == return_id, TaxReturn.company_id == company_id))
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="消費税申告が見つかりません")
    return _to_response(tr)


@router.post("/records/{return_id}/transition", response_model=TaxReturnResponse)
async def transition_tax_return(
    return_id: UUID,
    action: str = Query(..., description="filed"),
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_POST)),
    db: AsyncSession = Depends(get_db),
) -> TaxReturnResponse:
    """消費税申告のステータスを変更する。"""
    result = await db.execute(select(TaxReturn).where(TaxReturn.return_id == return_id, TaxReturn.company_id == company_id))
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="消費税申告が見つかりません")

    allowed = VALID_TRANSITIONS.get(tr.status, set())
    if action not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"現在のステータス「{tr.status}」から「{action}」への遷移は許可されていません",
        )

    tr.status = action
    await db.commit()
    await db.refresh(tr)
    return _to_response(tr)


@router.get("/records/{return_id}/export", response_class=PlainTextResponse)
async def export_tax_return(
    return_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> str:
    """消費税申告をCSV形式で出力する。"""
    result = await db.execute(scope_to_tenant(
        select(TaxReturn).where(
            TaxReturn.return_id == return_id,
        ),
        TaxReturn,
        current_user.tenant_id,
    ))
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="消費税申告が見つかりません")

    filing_label = "一般課税" if tr.filing_type == "general" else "簡易課税"

    # 金額は負数になりうる（調整額等）。csv_lineは数値を数式扱いしないため値を壊さない。
    rows: list[list[object]] = [
        ["項目", "金額"],
        ["申告年度", tr.tax_year],
        ["申告区分", filing_label],
        ["ステータス", tr.status],
        [],
        ["【売上】"],
        ["課税売上", tr.taxable_sales],
        ["非課税売上", tr.non_taxable_sales],
        ["輸出等免税売上", tr.export_taxable_sales],
        ["売上合計", tr.total_sales],
        [],
        ["【仕入】"],
        ["課税仕入", tr.purchases_subject_to_tax],
        ["不課税仕入", tr.purchases_not_subject_to_tax],
        ["仕入合計", tr.total_purchases],
        [],
        ["【消費税】"],
        ["売上税額", tr.output_tax],
        ["仕入税額", tr.input_tax],
        ["調整額", tr.tax_adjustment],
        ["納付税額", tr.tax_payable],
    ]

    return "\n".join(csv_line(row) for row in rows)
