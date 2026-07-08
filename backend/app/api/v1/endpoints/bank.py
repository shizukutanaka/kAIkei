from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import BankStatementDetail, Invoice, PaymentRequest
from app.schemas.schemas import BankReconcileRequest, BankReconciliationCandidate, BankReconciliationItem
from app.services.bank_reconciliation import BankReconciliationService

router = APIRouter()


@router.post("/reconcile", response_model=list[BankReconciliationItem])
async def reconcile_bank(
    payload: BankReconcileRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[BankReconciliationItem]:
    stmt = select(BankStatementDetail).where(
        BankStatementDetail.company_id == payload.company_id,
        BankStatementDetail.is_reconciled == False,  # noqa: E712
    )
    if payload.bank_account_id is not None:
        stmt = stmt.where(BankStatementDetail.bank_account_id == payload.bank_account_id)
    if payload.date_from is not None:
        stmt = stmt.where(BankStatementDetail.value_date >= payload.date_from)
    if payload.date_to is not None:
        stmt = stmt.where(BankStatementDetail.value_date <= payload.date_to)
    stmt = stmt.order_by(BankStatementDetail.value_date, BankStatementDetail.created_at)
    statement_result = await db.execute(stmt)
    statements = statement_result.scalars().all()

    invoice_query = select(Invoice).where(Invoice.company_id == payload.company_id)
    if payload.date_from is not None:
        invoice_query = invoice_query.where(Invoice.due_date >= payload.date_from)
    if payload.date_to is not None:
        invoice_query = invoice_query.where(Invoice.due_date <= payload.date_to)
    invoice_query = invoice_query.where(Invoice.status.in_(("issued", "paid")))
    invoices = (await db.execute(invoice_query)).scalars().all()

    payment_query = select(PaymentRequest).where(PaymentRequest.company_id == payload.company_id)
    if payload.date_from is not None:
        payment_query = payment_query.where(PaymentRequest.payment_date >= payload.date_from)
    if payload.date_to is not None:
        payment_query = payment_query.where(PaymentRequest.payment_date <= payload.date_to)
    payment_query = payment_query.where(PaymentRequest.status.in_(("approved", "executed")))
    payment_requests = (await db.execute(payment_query)).scalars().all()

    response: list[BankReconciliationItem] = []
    for statement in statements:
        candidates = BankReconciliationService.rank_candidates(statement, invoices, payment_requests)
        response.append(
            BankReconciliationItem(
                statement_detail_id=statement.statement_detail_id,
                candidates=[
                    BankReconciliationCandidate(
                        source_id=c.source_id,
                        source_type=c.source_type,
                        source_date=c.source_date,
                        amount=c.amount,
                        score=c.score,
                        reason=c.reason,
                    )
                    for c in candidates
                ],
            )
        )
    return response
