from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import PaymentRequest
from app.schemas.schemas import (
    PaymentMatchingRequest,
    PaymentMatchingResponse,
    PaymentRequestCreate,
    PaymentRequestResponse,
    ReceivableJournalDraftSchema,
    ReceivableJournalResponse,
    ReceivableMatchingRequest,
    ReceivableMatchingResponse,
    ZenginTransferRequest,
    ZenginTransferResponse,
)
from app.services.payment_matching import (
    BankWithdrawal,
    ExpectedPayment,
    PaymentMatchingService,
)
from app.services.payment_terms import PaymentTermsService
from app.services.payment_workflow import next_payment_status
from app.services.receivable_journal_draft import ReceivableJournalDraftService
from app.services.receivable_matching import (
    Deposit,
    OpenInvoice,
    ReceivableMatchingService,
)
from app.services.zengin_transfer import (
    TransferLine,
    TransferRequest,
    ZenginTransferService,
)

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


@router.post("/bank-matching", response_model=PaymentMatchingResponse)
async def match_payments_with_bank_withdrawals(
    payload: PaymentMatchingRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
) -> PaymentMatchingResponse:
    try:
        result = PaymentMatchingService.match(
            withdrawals=[
                BankWithdrawal(
                    line_id=item.line_id,
                    transaction_date=item.transaction_date,
                    amount=item.amount,
                    description=item.description,
                )
                for item in payload.withdrawals
            ],
            payments=[
                ExpectedPayment(
                    payment_id=item.payment_id,
                    payee_name=item.payee_name,
                    amount=item.amount,
                    payment_date=item.payment_date,
                )
                for item in payload.payments
            ],
            date_tolerance_days=payload.date_tolerance_days,
            fee_tolerance=payload.fee_tolerance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PaymentMatchingResponse.model_validate(result)


@router.post("/receivable-matching", response_model=ReceivableMatchingResponse)
async def match_deposits_with_invoices(
    payload: ReceivableMatchingRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
) -> ReceivableMatchingResponse:
    try:
        result = ReceivableMatchingService.match(
            deposits=[
                Deposit(
                    deposit_id=item.deposit_id,
                    transaction_date=item.transaction_date,
                    amount=item.amount,
                    remitter_name=item.remitter_name,
                )
                for item in payload.deposits
            ],
            invoices=[
                OpenInvoice(
                    invoice_id=item.invoice_id,
                    customer_name=item.customer_name,
                    amount=item.amount,
                    due_date=item.due_date,
                )
                for item in payload.invoices
            ],
            fee_tolerance=payload.fee_tolerance,
            name_threshold=payload.name_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ReceivableMatchingResponse.model_validate(result)


@router.post("/receivable-journal-drafts", response_model=ReceivableJournalResponse)
async def generate_receivable_journal_drafts(
    payload: ReceivableMatchingRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
) -> ReceivableJournalResponse:
    """入金明細と請求を消し込み、売掛金の消込仕訳ドラフトまで生成する。"""
    try:
        matched = ReceivableMatchingService.match(
            deposits=[
                Deposit(
                    deposit_id=item.deposit_id,
                    transaction_date=item.transaction_date,
                    amount=item.amount,
                    remitter_name=item.remitter_name,
                )
                for item in payload.deposits
            ],
            invoices=[
                OpenInvoice(
                    invoice_id=item.invoice_id,
                    customer_name=item.customer_name,
                    amount=item.amount,
                    due_date=item.due_date,
                )
                for item in payload.invoices
            ],
            fee_tolerance=payload.fee_tolerance,
            name_threshold=payload.name_threshold,
        )
        journal = ReceivableJournalDraftService.generate(
            matched,
            transaction_dates={
                item.deposit_id: item.transaction_date for item in payload.deposits
            },
            partner_names={
                item.invoice_id: item.customer_name for item in payload.invoices
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ReceivableJournalResponse(
        matching=ReceivableMatchingResponse.model_validate(matched),
        drafts=[ReceivableJournalDraftSchema.model_validate(d) for d in journal.drafts],
        total_receivable_cleared=journal.total_receivable_cleared,
        total_fee_expense=journal.total_fee_expense,
        total_advance_received=journal.total_advance_received,
        total_suspense=journal.total_suspense,
        balanced=journal.balanced,
    )


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
