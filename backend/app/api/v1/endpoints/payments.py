from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import PaymentRequest
from app.schemas.schemas import PaymentRequestCreate, PaymentRequestResponse, ZenginExportRequest
from app.services.payment_export import ZenginExportService
from app.services.payment_terms import PaymentTermsService
from app.services.payment_workflow import next_payment_status

router = APIRouter()


@router.get("", response_model=list[PaymentRequestResponse])
async def list_payment_requests(
    company_id: UUID = Query(...),  # noqa: B008
    status: str | None = Query(None, description="draft/approved/executed/cancelled"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[PaymentRequestResponse]:
    """会社の支払申請を一覧取得する（任意でステータス絞り込み）。"""
    stmt = select(PaymentRequest).where(PaymentRequest.company_id == company_id)
    if status is not None:
        stmt = stmt.where(PaymentRequest.status == status)
    stmt = stmt.order_by(PaymentRequest.payment_date.asc(), PaymentRequest.created_at.asc())
    result = await db.execute(stmt)
    return [PaymentRequestResponse.model_validate(r) for r in result.scalars().all()]


async def _transition(db: AsyncSession, company_id: UUID, request_id: UUID, action: str) -> PaymentRequest:
    result = await db.execute(
        select(PaymentRequest).where(
            PaymentRequest.payment_request_id == request_id,
            PaymentRequest.company_id == company_id,
        )
    )
    request = result.scalar_one_or_none()
    if request is None:
        raise HTTPException(status_code=404, detail="Payment request not found")
    try:
        request.status = next_payment_status(request.status, action)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.flush()
    await db.refresh(request)
    return request


@router.post("", response_model=PaymentRequestResponse, status_code=201)
async def create_payment_request(
    payload: PaymentRequestCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> PaymentRequestResponse:
    request = PaymentRequest(
        company_id=payload.company_id,
        partner_id=payload.partner_id,
        payment_date=payload.payment_date,
        payment_amount=payload.payment_amount,
        bank_account_id=payload.bank_account_id,
        dest_bank_code=payload.dest_bank_code,
        dest_branch_code=payload.dest_branch_code,
        dest_account_type=payload.dest_account_type,
        dest_account_no=payload.dest_account_no,
        dest_account_name_kana=payload.dest_account_name_kana,
        status="draft",
        created_by=current_user.user_id,
    )
    db.add(request)
    await db.flush()
    await db.refresh(request)
    return PaymentRequestResponse.model_validate(request)


@router.post("/{request_id}/approve", response_model=PaymentRequestResponse)
async def approve_payment_request(
    request_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_UPDATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> PaymentRequestResponse:
    """下書きの支払申請を承認する（draft→approved）。"""
    return PaymentRequestResponse.model_validate(await _transition(db, company_id, request_id, "approve"))


@router.post("/{request_id}/execute", response_model=PaymentRequestResponse)
async def execute_payment_request(
    request_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_UPDATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> PaymentRequestResponse:
    """承認済みの支払申請を実行済みにする（approved→executed）。"""
    return PaymentRequestResponse.model_validate(await _transition(db, company_id, request_id, "execute"))


@router.post("/{request_id}/cancel", response_model=PaymentRequestResponse)
async def cancel_payment_request(
    request_id: UUID,
    company_id: UUID = Query(...),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_UPDATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> PaymentRequestResponse:
    """支払申請を取り消す（draft/approved→cancelled）。"""
    return PaymentRequestResponse.model_validate(await _transition(db, company_id, request_id, "cancel"))


@router.post("/zengin-export")
async def export_zengin(
    payload: ZenginExportRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> Response:
    stmt = select(PaymentRequest).where(
        PaymentRequest.company_id == payload.company_id,
        PaymentRequest.payment_date == payload.payment_date,
        PaymentRequest.bank_account_id == payload.bank_account_id,
        PaymentRequest.status.in_(("approved", "executed")),
    )
    if payload.payment_request_ids:
        stmt = stmt.where(PaymentRequest.payment_request_id.in_(payload.payment_request_ids))
    result = await db.execute(stmt)
    requests = result.scalars().all()
    body = ZenginExportService.render(
        requests=requests,
        company_id=payload.company_id,
        payment_date=payload.payment_date.isoformat(),
        bank_account_id=payload.bank_account_id,
    )
    return Response(content=body, media_type="application/octet-stream")


@router.get("/payment-date")
async def get_payment_date(
    invoice_date: date = Query(..., description="請求日"),  # noqa: B008
    closing_day: int = Query(..., ge=1, le=31, description="締め日"),  # noqa: B008
    payment_month_offset: int = Query(1, ge=0, description="支払月オフセット"),  # noqa: B008
    payment_day: int = Query(..., ge=1, le=31, description="支払日"),  # noqa: B008
    adjustment: str = Query("next", description="next, previous, none"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
) -> dict[str, object]:
    try:
        closing_date = PaymentTermsService.compute_closing_date(invoice_date, closing_day)
        payment_date = PaymentTermsService.compute_payment_date(
            invoice_date=invoice_date,
            closing_day=closing_day,
            payment_month_offset=payment_month_offset,
            payment_day=payment_day,
            holidays=None,
            adjustment=adjustment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "invoice_date": invoice_date,
        "closing_date": closing_date,
        "payment_date": payment_date,
    }
