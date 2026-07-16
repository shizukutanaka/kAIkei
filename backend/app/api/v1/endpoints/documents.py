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
from app.schemas.schemas import (
    ArchivedDocumentResponse,
    DenchouElectronicCheckRequest,
    DenchouElectronicCheckResponse,
    DenchouScannerCheckRequest,
    DenchouScannerCheckResponse,
)
from app.services.denchou_electronic import DenchouElectronicService
from app.services.denchou_scanner import DenchouScannerService
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


@router.post("/denchou/electronic-transaction/check", response_model=DenchouElectronicCheckResponse)
async def check_denchou_electronic_transaction(
    payload: DenchouElectronicCheckRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
) -> DenchouElectronicCheckResponse:
    try:
        result = DenchouElectronicService.check(
            has_timestamp=payload.has_timestamp,
            has_correction_deletion_history=payload.has_correction_deletion_history,
            has_operational_rules=payload.has_operational_rules,
            has_display_device=payload.has_display_device,
            can_search_by_date=payload.can_search_by_date,
            can_search_by_amount=payload.can_search_by_amount,
            can_search_by_counterparty=payload.can_search_by_counterparty,
            can_search_by_range=payload.can_search_by_range,
            can_search_by_combination=payload.can_search_by_combination,
            base_period_sales=payload.base_period_sales,
            can_provide_download=payload.can_provide_download,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DenchouElectronicCheckResponse.model_validate(result)


@router.post("/denchou/scanner-storage/check", response_model=DenchouScannerCheckResponse)
async def check_denchou_scanner_storage(
    payload: DenchouScannerCheckRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
) -> DenchouScannerCheckResponse:
    try:
        result = DenchouScannerService.check(
            resolution_dpi=payload.resolution_dpi,
            is_color=payload.is_color,
            is_general_document=payload.is_general_document,
            input_period_type=payload.input_period_type,
            days_until_input=payload.days_until_input,
            has_operational_rules=payload.has_operational_rules,
            has_timestamp=payload.has_timestamp,
            has_correction_deletion_history=payload.has_correction_deletion_history,
            has_display_device=payload.has_display_device,
            can_search_by_date=payload.can_search_by_date,
            can_search_by_amount=payload.can_search_by_amount,
            can_search_by_counterparty=payload.can_search_by_counterparty,
            can_search_by_range=payload.can_search_by_range,
            can_search_by_combination=payload.can_search_by_combination,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DenchouScannerCheckResponse.model_validate(result)
