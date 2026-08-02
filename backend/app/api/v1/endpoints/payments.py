from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import PaymentRequest
from app.schemas.schemas import (
    PaymentRequestCreate,
    PaymentRequestResponse,
    ZenginExportRequest,
    ZenginTransferRequest,
    ZenginTransferResponse,
)
from app.services.payment_export import ZenginExportService
from app.services.payment_terms import PaymentTermsService
from app.services.zengin_transfer import (
    TransferLine,
    TransferRequest,
    ZenginTransferService,
)

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


@router.post("/zengin/transfer-data", response_model=ZenginTransferResponse)
async def generate_zengin_transfer_data(
    payload: ZenginTransferRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
) -> ZenginTransferResponse:
    try:
        result = ZenginTransferService.generate(
            TransferRequest(
                consignor_code=payload.consignor_code,
                consignor_name=payload.consignor_name,
                transfer_date=payload.transfer_date,
                bank_code=payload.bank_code,
                bank_name=payload.bank_name,
                branch_code=payload.branch_code,
                branch_name=payload.branch_name,
                account_type=payload.account_type,
                account_number=payload.account_number,
                lines=[
                    TransferLine(
                        bank_code=line.bank_code,
                        bank_name=line.bank_name,
                        branch_code=line.branch_code,
                        branch_name=line.branch_name,
                        account_type=line.account_type,
                        account_number=line.account_number,
                        recipient_name=line.recipient_name,
                        amount=line.amount,
                        customer_code=line.customer_code,
                        fee_borne_by_recipient=line.fee_borne_by_recipient,
                        transfer_fee=line.transfer_fee,
                    )
                    for line in payload.lines
                ],
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ZenginTransferResponse.model_validate(result)


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
