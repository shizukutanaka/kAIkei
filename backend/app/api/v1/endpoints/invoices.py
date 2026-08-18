from contextlib import suppress
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.csv_export import csv_line
from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission, verified_company_id
from app.core.rbac import Permission
from app.models.models import Invoice, InvoiceLine, Partner
from app.schemas.schemas import (
    CreditCheckRequest,
    CreditCheckResponse,
    InvoiceCreate,
    InvoiceLineResponse,
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceTaxComputeRequest,
    InvoiceTaxComputeResponse,
    NotificationCreate,
    OrderFulfillmentRequest,
    OrderFulfillmentResponse,
    QualifiedInvoiceCheckRequest,
    QualifiedInvoiceCheckResponse,
    ReceivableAgingRequest,
    ReceivableAgingResponse,
    SalesClosingRequest,
    SalesClosingResponse,
)
from app.services.auto_journal import (
    generate_invoice_issue_journal,
    generate_invoice_payment_journal,
)
from app.services.credit_limit import CreditLimitService, CreditRequest
from app.services.invoice_number import is_valid_registration_number, normalize
from app.services.invoice_tax import InvoiceTaxService
from app.services.notification_service import create_notification
from app.services.order_fulfillment import Order, OrderFulfillmentService, Shipment
from app.services.qualified_invoice_check import (
    QualifiedInvoiceCheckService,
    QualifiedInvoiceInput,
    QualifiedInvoiceLine,
)
from app.services.receivable_aging import ReceivableAgingService, ReceivableItem
from app.services.sales_closing import (
    BillingTerms,
    SalesClosingService,
    SalesLine,
)

router = APIRouter()


@router.get("/validate-registration-number")
async def validate_registration_number(
    number: str = Query(..., description="インボイス登録番号（例: T1234567890123）"),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
) -> dict:
    """適格請求書発行事業者番号の書式・検査用数字をローカル検証する。"""
    return {"number": normalize(number), "is_valid": is_valid_registration_number(number)}

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
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
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


@router.get("/invoices", response_model=InvoiceListResponse)
async def list_invoices(
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    status: str | None = Query(None),  # noqa: B008
    partner_id: UUID | None = Query(None),  # noqa: B008
    page: int = Query(1, ge=1),  # noqa: B008
    page_size: int = Query(50, ge=1, le=200),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> InvoiceListResponse:
    """請求書一覧を取得する（ページネーション対応）。"""
    base_query = (
        select(Invoice, Partner.partner_name)
        .outerjoin(Partner, Invoice.partner_id == Partner.partner_id)
        .where(Invoice.company_id == company_id)
        .options(selectinload(Invoice.lines))
    )
    if status:
        base_query = base_query.where(Invoice.status == status)
    if partner_id:
        base_query = base_query.where(Invoice.partner_id == partner_id)

    # Count total
    count_query = (
        select(func.count())
        .select_from(Invoice)
        .where(Invoice.company_id == company_id)
    )
    if status:
        count_query = count_query.where(Invoice.status == status)
    if partner_id:
        count_query = count_query.where(Invoice.partner_id == partner_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginated query
    query = base_query.order_by(Invoice.invoice_date.desc(), Invoice.invoice_number).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.all()
    items = [_to_response(inv, name) for inv, name in rows]

    return InvoiceListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/check-qualified", response_model=QualifiedInvoiceCheckResponse)
async def check_qualified_invoice(
    payload: QualifiedInvoiceCheckRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> QualifiedInvoiceCheckResponse:
    invoice = QualifiedInvoiceInput(
        issuer_name=payload.issuer_name,
        registration_number=payload.registration_number,
        transaction_date=payload.transaction_date,
        recipient_name=payload.recipient_name,
        line_items=[
            QualifiedInvoiceLine(description=line.description, tax_rate=line.tax_rate)
            for line in payload.line_items
        ],
        tax_by_rate={item.tax_rate: item.tax_amount for item in payload.tax_by_rate},
    )
    result = QualifiedInvoiceCheckService.check(invoice)
    return QualifiedInvoiceCheckResponse(
        is_valid=result.is_valid,
        missing_fields=result.missing_fields,
        registration_number_valid=result.registration_number_valid,
    )


@router.post("/compute-tax", response_model=InvoiceTaxComputeResponse)
async def compute_invoice_tax(
    payload: InvoiceTaxComputeRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> InvoiceTaxComputeResponse:
    try:
        result = InvoiceTaxService.compute_invoice_tax(payload.lines)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return InvoiceTaxComputeResponse(
        by_rate=[
            {
                "tax_rate": entry.tax_rate,
                "taxable_base": entry.taxable_base,
                "tax": entry.tax,
            }
            for entry in result.by_rate
        ],
        total_taxable=result.total_taxable,
        total_tax=result.total_tax,
        total_amount=result.total_amount,
    )


@router.post("/receivable-aging", response_model=ReceivableAgingResponse)
async def analyze_receivable_aging(
    payload: ReceivableAgingRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> ReceivableAgingResponse:
    """売掛金の滞留状況を区分し、取引先単位の督促タスクを生成する。"""
    try:
        result = ReceivableAgingService.analyze(
            as_of=payload.as_of,
            receivables=[
                ReceivableItem(
                    invoice_id=item.invoice_id,
                    customer_code=item.customer_code,
                    customer_name=item.customer_name,
                    due_date=item.due_date,
                    amount=item.amount,
                    paid_amount=item.paid_amount,
                )
                for item in payload.receivables
            ],
            minimum_amount=payload.minimum_amount,
            statute_alert_days=payload.statute_alert_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ReceivableAgingResponse.model_validate(result)


@router.post("/credit-check", response_model=CreditCheckResponse)
async def check_credit_limits(
    payload: CreditCheckRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> CreditCheckResponse:
    """受注額を含む与信使用額と滞留状況から、取引先ごとの受注可否を判定する。"""
    try:
        result = CreditLimitService.check(
            as_of=payload.as_of,
            requests=[
                CreditRequest(
                    customer_code=item.customer_code,
                    customer_name=item.customer_name,
                    order_amount=item.order_amount,
                    credit_limit=item.credit_limit,
                    receivable_balance=item.receivable_balance,
                    order_backlog=item.order_backlog,
                    notes_receivable=item.notes_receivable,
                    advance_received=item.advance_received,
                    temporary_limit=item.temporary_limit,
                    temporary_limit_expiry=item.temporary_limit_expiry,
                    max_days_overdue=item.max_days_overdue,
                    has_default_event=item.has_default_event,
                )
                for item in payload.requests
            ],
            warning_ratio=payload.warning_ratio,
            blocking_days_overdue=payload.blocking_days_overdue,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CreditCheckResponse.model_validate(result)


@router.post("/order-fulfillment", response_model=OrderFulfillmentResponse)
async def process_order_fulfillment(
    payload: OrderFulfillmentRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> OrderFulfillmentResponse:
    """受注と出荷実績から売上計上明細・受注残・納期遅延を導出する。"""
    try:
        result = OrderFulfillmentService.process(
            as_of=payload.as_of,
            orders=[
                Order(
                    order_id=item.order_id,
                    customer_code=item.customer_code,
                    customer_name=item.customer_name,
                    order_date=item.order_date,
                    delivery_date=item.delivery_date,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    tax_rate=item.tax_rate,
                    description=item.description,
                    credit_status=item.credit_status,
                )
                for item in payload.orders
            ],
            shipments=[
                Shipment(
                    shipment_id=item.shipment_id,
                    order_id=item.order_id,
                    shipped_date=item.shipped_date,
                    quantity=item.quantity,
                )
                for item in payload.shipments
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OrderFulfillmentResponse.model_validate(result)


@router.post("/sales-closing", response_model=SalesClosingResponse)
async def close_sales_into_invoices(
    payload: SalesClosingRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> SalesClosingResponse:
    """売上明細を締めて請求・売上計上仕訳・入金予定日を生成する。"""
    try:
        result = SalesClosingService.close(
            lines=[
                SalesLine(
                    line_id=item.line_id,
                    customer_code=item.customer_code,
                    customer_name=item.customer_name,
                    sales_date=item.sales_date,
                    amount=item.amount,
                    tax_rate=item.tax_rate,
                    description=item.description,
                )
                for item in payload.lines
            ],
            terms=[
                BillingTerms(
                    customer_code=item.customer_code,
                    closing_day=item.closing_day,
                    payment_month_offset=item.payment_month_offset,
                    payment_day=item.payment_day,
                    adjustment=item.adjustment,
                )
                for item in payload.terms
            ],
            holidays=set(payload.holidays),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SalesClosingResponse.model_validate(result)


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> InvoiceResponse:
    """請求書詳細を取得する。"""
    result = await db.execute(
        select(Invoice, Partner.partner_name)
        .outerjoin(Partner, Invoice.partner_id == Partner.partner_id)
        .where(Invoice.invoice_id == invoice_id, Invoice.company_id == company_id)
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
    action: str = Query(..., description="issued, paid, cancelled"),  # noqa: B008
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_POST)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> InvoiceResponse:
    """請求書のステータスを変更する。"""
    result = await db.execute(
        select(Invoice, Partner.partner_name)
        .outerjoin(Partner, Invoice.partner_id == Partner.partner_id)
        .where(Invoice.invoice_id == invoice_id, Invoice.company_id == company_id)
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

    # Auto-generate journal entries on status transitions
    if action == "issued":
        with suppress(ValueError):
            await generate_invoice_issue_journal(
                db,
                company_id=inv.company_id,
                invoice_number=inv.invoice_number,
                invoice_date=inv.invoice_date,
                subtotal=inv.subtotal,
                tax_amount=inv.tax_amount,
                total_amount=inv.total_amount,
                created_by=current_user.user_id,
            )
    elif action == "paid":
        with suppress(ValueError):
            await generate_invoice_payment_journal(
                db,
                company_id=inv.company_id,
                invoice_number=inv.invoice_number,
                payment_date=inv.invoice_date,
                total_amount=inv.total_amount,
                created_by=current_user.user_id,
            )

    # Notify on invoice transition
    action_labels = {"issued": "発行", "paid": "入金確認", "cancelled": "キャンセル"}
    with suppress(Exception):
        await create_notification(
            db,
            current_user.tenant_id,
            NotificationCreate(
                company_id=inv.company_id,
                category="invoice",
                priority="high" if action == "paid" else "normal",
                title=f"請求書 {inv.invoice_number} {action_labels[action]}",
                body=f"請求書 {inv.invoice_number} を{action_labels[action]}しました。",
                action_url="/invoices",
            ),
        )

    await db.commit()
    await db.refresh(inv, attribute_names=["lines"])
    return _to_response(inv, name)


@router.get("/invoices/{invoice_id}/export", response_class=PlainTextResponse)
async def export_invoice(
    invoice_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
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

    # 取引先名・明細の内容は自由入力のため、csv_lineで列ずれと数式化を防ぐ。
    rows: list[list[object]] = [
        ["項目", "内容"],
        ["請求書番号", inv.invoice_number],
        ["請求日", inv.invoice_date],
        ["支払期限", inv.due_date],
        ["取引先コード", partner_code or ""],
        ["取引先名", partner_name or ""],
        ["ステータス", inv.status],
        ["税率", f"{inv.tax_rate}%"],
        [],
        ["No", "内容", "数量", "単価", "金額"],
    ]

    for ln in inv.lines:
        rows.append([ln.line_number, ln.description, ln.quantity, ln.unit_price, ln.line_total])

    rows.append([])
    rows.append(["小計", inv.subtotal])
    rows.append(["消費税", inv.tax_amount])
    rows.append(["合計", inv.total_amount])

    return "\n".join(csv_line(row) for row in rows)


@router.get("/invoices/{invoice_id}/peppol-xml", response_class=PlainTextResponse)
async def export_invoice_peppol(
    invoice_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """請求書を Peppol / JP PINT 準拠の UBL Invoice XML で出力する。"""
    from app.models.models import Company
    from app.services.peppol_export import UblInvoice, UblLine, build_ubl_invoice

    result = await db.execute(
        select(Invoice, Partner.partner_name)
        .outerjoin(Partner, Invoice.partner_id == Partner.partner_id)
        .where(Invoice.invoice_id == invoice_id)
        .options(selectinload(Invoice.lines))
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="請求書が見つかりません")
    inv, partner_name = row

    company = await db.get(Company, inv.company_id)

    ubl = UblInvoice(
        invoice_number=inv.invoice_number,
        issue_date=inv.invoice_date,
        due_date=inv.due_date,
        supplier_name=company.company_name if company else "",
        customer_name=partner_name or "",
        subtotal=inv.subtotal,
        tax_rate=inv.tax_rate,
        tax_amount=inv.tax_amount,
        total_amount=inv.total_amount,
        supplier_registration_number=company.invoice_registration_number if company else None,
        lines=[
            UblLine(str(ln.line_id), ln.description, ln.quantity, ln.unit_price, ln.line_total)
            for ln in inv.lines
        ],
    )
    xml = build_ubl_invoice(ubl)
    return Response(content=xml, media_type="application/xml")


@router.get("/stats", response_model=dict)
async def invoice_stats(
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    year: int = Query(...),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
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
