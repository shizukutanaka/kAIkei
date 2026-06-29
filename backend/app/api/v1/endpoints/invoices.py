from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Invoice, InvoiceLine, Partner
from app.schemas.schemas import (
    InvoiceCreate,
    InvoiceResponse,
    InvoiceLineResponse,
)

router = APIRouter()

VALID_INVOICE_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"issued"},
    "issued": {"paid", "cancelled"},
    "paid": set(),
    "cancelled": set(),
}


def _round2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _to_response(inv: Invoice, partner_name: str | None = None) -> InvoiceResponse:
    return InvoiceResponse(
        invoice_id=inv.invoice_id,
        company_id=inv.company_id,
        partner_id=inv.partner_id,
        invoice_number=inv.invoice_number,
        invoice_date=inv.invoice_date,
        due_date=inv.due_date,
        subtotal=inv.subtotal,
        tax_rate=inv.tax_rate,
        tax_amount=inv.tax_amount,
        total_amount=inv.total_amount,
        status=inv.status,
        note=inv.note,
        partner_name=partner_name,
        lines=[
            InvoiceLineResponse(
                line_id=ln.line_id,
                line_number=ln.line_number,
                description=ln.description,
                quantity=ln.quantity,
                unit_price=ln.unit_price,
                line_total=ln.line_total,
            )
            for ln in inv.lines
        ],
    )


@router.post("/invoices", response_model=InvoiceResponse, status_code=201)
async def create_invoice(
    payload: InvoiceCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> InvoiceResponse:
    """請求書を作成する。"""
    if not payload.lines:
        raise HTTPException(status_code=422, detail="明細が空です")

    if payload.due_date < payload.invoice_date:
        raise HTTPException(status_code=422, detail="支払期限が請求日より前です")

    existing = await db.execute(
        select(Invoice).where(
            Invoice.company_id == payload.company_id,
            Invoice.invoice_number == payload.invoice_number,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"請求書番号「{payload.invoice_number}」は既に存在します")

    subtotal = Decimal("0")
    for line in payload.lines:
        line_total = _round2(line.quantity * line.unit_price)
        subtotal += line_total

    tax_amount = _round2(subtotal * payload.tax_rate / Decimal("100"))
    total_amount = subtotal + tax_amount

    inv = Invoice(
        company_id=payload.company_id,
        partner_id=payload.partner_id,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        subtotal=subtotal,
        tax_rate=payload.tax_rate,
        tax_amount=tax_amount,
        total_amount=total_amount,
        status="draft",
        note=payload.note,
    )
    db.add(inv)
    await db.flush()

    for idx, line in enumerate(payload.lines, start=1):
        line_total = _round2(line.quantity * line.unit_price)
        db.add(InvoiceLine(
            invoice_id=inv.invoice_id,
            line_number=idx,
            description=line.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            line_total=line_total,
        ))

    await db.commit()
    await db.refresh(inv, attribute_names=["lines"])

    partner_name = None
    if inv.partner_id:
        p = await db.execute(select(Partner.partner_name).where(Partner.partner_id == inv.partner_id))
        partner_name = p.scalar_one_or_none()

    return _to_response(inv, partner_name)


@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    company_id: UUID = Query(...),
    status: str | None = Query(None),
    partner_id: UUID | None = Query(None),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[InvoiceResponse]:
    """請求書一覧を取得する。"""
    query = (
        select(Invoice, Partner.partner_name)
        .outerjoin(Partner, Invoice.partner_id == Partner.partner_id)
        .where(Invoice.company_id == company_id)
        .options(selectinload(Invoice.lines))
        .order_by(Invoice.invoice_date.desc(), Invoice.invoice_number)
    )
    if status:
        query = query.where(Invoice.status == status)
    if partner_id:
        query = query.where(Invoice.partner_id == partner_id)

    result = await db.execute(query)
    rows = result.all()
    return [_to_response(inv, name) for inv, name in rows]


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> InvoiceResponse:
    """請求書詳細を取得する。"""
    result = await db.execute(
        select(Invoice, Partner.partner_name)
        .outerjoin(Partner, Invoice.partner_id == Partner.partner_id)
        .where(Invoice.invoice_id == invoice_id)
        .options(selectinload(Invoice.lines))
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="請求書が見つかりません")
    inv, name = row
    return _to_response(inv, name)


@router.post("/invoices/{invoice_id}/transition", response_model=InvoiceResponse)
async def transition_invoice(
    invoice_id: UUID,
    action: str = Query(..., description="issued, paid, cancelled"),
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_POST)),
    db: AsyncSession = Depends(get_db),
) -> InvoiceResponse:
    """請求書のステータスを変更する。"""
    result = await db.execute(
        select(Invoice, Partner.partner_name)
        .outerjoin(Partner, Invoice.partner_id == Partner.partner_id)
        .where(Invoice.invoice_id == invoice_id)
        .options(selectinload(Invoice.lines))
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="請求書が見つかりません")

    inv, name = row
    allowed = VALID_INVOICE_TRANSITIONS.get(inv.status, set())
    if action not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"現在のステータス「{inv.status}」から「{action}」への遷移は許可されていません",
        )

    inv.status = action
    await db.commit()
    await db.refresh(inv, attribute_names=["lines"])
    return _to_response(inv, name)


@router.get("/invoices/{invoice_id}/export", response_class=PlainTextResponse)
async def export_invoice(
    invoice_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> str:
    """請求書をCSV形式で出力する。"""
    result = await db.execute(
        select(Invoice, Partner.partner_name, Partner.partner_code)
        .outerjoin(Partner, Invoice.partner_id == Partner.partner_id)
        .where(Invoice.invoice_id == invoice_id)
        .options(selectinload(Invoice.lines))
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="請求書が見つかりません")

    inv, partner_name, partner_code = row

    lines = [
        "項目,内容",
        f"請求書番号,{inv.invoice_number}",
        f"請求日,{inv.invoice_date}",
        f"支払期限,{inv.due_date}",
        f"取引先コード,{partner_code or ''}",
        f"取引先名,{partner_name or ''}",
        f"ステータス,{inv.status}",
        f"税率,{inv.tax_rate}%",
        "",
        "No,内容,数量,単価,金額",
    ]

    for ln in inv.lines:
        lines.append(f"{ln.line_number},{ln.description},{ln.quantity},{ln.unit_price},{ln.line_total}")

    lines.append("")
    lines.append(f"小計,{inv.subtotal}")
    lines.append(f"消費税,{inv.tax_amount}")
    lines.append(f"合計,{inv.total_amount}")

    return "\n".join(lines)


@router.get("/stats", response_model=dict)
async def invoice_stats(
    company_id: UUID = Query(...),
    year: int = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """年次の請求書統計を取得する。"""
    result = await db.execute(
        select(
            func.count(Invoice.invoice_id).label("count"),
            func.coalesce(func.sum(Invoice.subtotal), 0).label("total_subtotal"),
            func.coalesce(func.sum(Invoice.tax_amount), 0).label("total_tax"),
            func.coalesce(func.sum(Invoice.total_amount), 0).label("total_amount"),
            func.count().filter(Invoice.status == "draft").label("draft_count"),
            func.count().filter(Invoice.status == "issued").label("issued_count"),
            func.count().filter(Invoice.status == "paid").label("paid_count"),
            func.count().filter(Invoice.status == "cancelled").label("cancelled_count"),
        ).where(
            Invoice.company_id == company_id,
            func.extract("year", Invoice.invoice_date) == year,
        )
    )
    row = result.one()
    return {
        "year": year,
        "count": row.count,
        "total_subtotal": str(row.total_subtotal),
        "total_tax": str(row.total_tax),
        "total_amount": str(row.total_amount),
        "draft_count": row.draft_count,
        "issued_count": row.issued_count,
        "paid_count": row.paid_count,
        "cancelled_count": row.cancelled_count,
    }
