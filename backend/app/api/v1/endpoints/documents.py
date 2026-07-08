"""Document archive endpoints."""

# ruff: noqa: B008

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.schemas.schemas import ArchivedDocumentResponse
from app.services.document_archive import DocumentArchiveService

router = APIRouter()
service = DocumentArchiveService()


@router.post("/archive", response_model=ArchivedDocumentResponse, status_code=status.HTTP_201_CREATED)
async def archive_document(
    file: UploadFile = File(...),
    company_id: UUID = Form(...),
    transaction_date: date = Form(...),
    transaction_amount: Decimal = Form(...),
    counterparty_name: str = Form(...),
    document_type: str = Form(default="other"),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ArchivedDocumentResponse:
    try:
        archived = await service.archive(
            db,
            company_id=company_id,
            file=file,
            transaction_date=transaction_date,
            transaction_amount=transaction_amount,
            counterparty_name=counterparty_name,
            document_type=document_type,
            created_by=current_user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ArchivedDocumentResponse.model_validate(archived)


@router.get("/search", response_model=list[ArchivedDocumentResponse])
async def search_documents(
    company_id: UUID = Query(...),
    transaction_date_from: date | None = Query(None),
    transaction_date_to: date | None = Query(None),
    amount_min: Decimal | None = Query(None),
    amount_max: Decimal | None = Query(None),
    counterparty_name: str | None = Query(None),
    document_type: str | None = Query(None),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[ArchivedDocumentResponse]:
    items = await service.search(
        db,
        company_id=company_id,
        transaction_date_from=transaction_date_from,
        transaction_date_to=transaction_date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        counterparty_name=counterparty_name,
        document_type=document_type,
    )
    return [ArchivedDocumentResponse.model_validate(item) for item in items]
