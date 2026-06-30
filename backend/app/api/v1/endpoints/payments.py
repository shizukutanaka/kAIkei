from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import PaymentRequest
from app.schemas.schemas import PaymentRequestCreate, PaymentRequestResponse, ZenginExportRequest
from app.services.payment_export import ZenginExportService

router = APIRouter()


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
