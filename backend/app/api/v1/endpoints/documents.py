from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission, verified_company_id
from app.core.rbac import Permission
from app.schemas.schemas import (
    ArchivedDocumentResponse,
    DenchouElectronicCheckRequest,
    DenchouElectronicCheckResponse,
    DenchouScannerCheckRequest,
    DenchouScannerCheckResponse,
    DocumentVerifyResponse,
)
from app.services import document_archive
from app.services.denchou_electronic import DenchouElectronicService
from app.services.denchou_scanner import DenchouScannerService

router = APIRouter()


@router.post("/extract")
async def extract_fields(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission(Permission.DOCUMENT_MANAGE)),
) -> dict:
    """アップロード証憑から検索3軸（取引年月日・金額・取引先）を自動抽出する。

    AIプロバイダ設定時はマルチモーダル/テキストLLM抽出＋regexマージ、
    未設定時はregex抽出のみで応答する（登録フォームのプリフィル用）。
    """
    from app.services.ai.document_extraction import extract_document_fields_from_pdf
    from app.services.ai.inference_engine import ai_engine

    file_bytes = await file.read()
    provider = ai_engine.document_extraction_provider
    fields = await extract_document_fields_from_pdf(file_bytes, provider=provider)
    fields["ai_used"] = provider is not None
    return fields


@router.post("", response_model=ArchivedDocumentResponse, status_code=status.HTTP_201_CREATED)
async def archive(
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    document_type: str = Form(...),
    transaction_date: date = Form(...),
    amount: Decimal | None = Form(None),
    counterparty_name: str | None = Form(None),
    linked_journal_header_id: UUID | None = Form(None),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission(Permission.DOCUMENT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ArchivedDocumentResponse:
    """証憑ファイルを電帳法アーカイブへ登録する（SHA-256ハッシュ付与）。"""
    file_bytes = await file.read()
    storage_path = document_archive.build_storage_key(
        current_user.tenant_id, company_id, transaction_date, file.filename or "document"
    )
    try:
        document = await document_archive.archive_document(
            db,
            tenant_id=current_user.tenant_id,
            company_id=company_id,
            document_type=document_type,
            file_name=file.filename or "document",
            file_bytes=file_bytes,
            transaction_date=transaction_date,
            storage_path=storage_path,
            amount=amount,
            counterparty_name=counterparty_name,
            mime_type=file.content_type,
            linked_journal_header_id=linked_journal_header_id,
            registered_by=current_user.user_id,
        )
    except document_archive.CompanyNotFoundError:
        raise HTTPException(status_code=404, detail="Company not found") from None
    return ArchivedDocumentResponse.model_validate(document)


@router.get("/search", response_model=list[ArchivedDocumentResponse])
async def search(
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    amount_min: Decimal | None = Query(None),
    amount_max: Decimal | None = Query(None),
    counterparty: str | None = Query(None),
    include_superseded: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    current_user: CurrentUser = Depends(require_permission(Permission.DOCUMENT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[ArchivedDocumentResponse]:
    """電帳法の検索3軸（日付・金額・取引先）で証憑を検索する。既定は現行版のみ。"""
    docs = await document_archive.search_documents(
        db,
        company_id=company_id,
        tenant_id=current_user.tenant_id,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        counterparty=counterparty,
        include_superseded=include_superseded,
        limit=limit,
    )
    return [ArchivedDocumentResponse.model_validate(d) for d in docs]


@router.post("/{document_id}/supersede", response_model=ArchivedDocumentResponse, status_code=status.HTTP_201_CREATED)
async def supersede(
    document_id: UUID,
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    document_type: str = Form(...),
    transaction_date: date = Form(...),
    amount: Decimal | None = Form(None),
    counterparty_name: str | None = Form(None),
    linked_journal_header_id: UUID | None = Form(None),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission(Permission.DOCUMENT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> ArchivedDocumentResponse:
    """既存証憑を差し替える。旧版は残し、新版へのリンク（訂正削除履歴）を張る。"""
    file_bytes = await file.read()
    storage_path = document_archive.build_storage_key(
        current_user.tenant_id, company_id, transaction_date, file.filename or "document"
    )
    try:
        result = await document_archive.supersede_document(
            db,
            tenant_id=current_user.tenant_id,
            company_id=company_id,
            old_document_id=document_id,
            document_type=document_type,
            file_name=file.filename or "document",
            file_bytes=file_bytes,
            transaction_date=transaction_date,
            storage_path=storage_path,
            amount=amount,
            counterparty_name=counterparty_name,
            mime_type=file.content_type,
            linked_journal_header_id=linked_journal_header_id,
            registered_by=current_user.user_id,
        )
    except document_archive.CompanyNotFoundError:
        raise HTTPException(status_code=404, detail="Company not found") from None
    if result is None:
        raise HTTPException(status_code=404, detail="Archived document not found")
    _old, new = result
    return ArchivedDocumentResponse.model_validate(new)


@router.get("/{document_id}/download")
async def download(
    document_id: UUID,
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.DOCUMENT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """保存済み証憑ファイル本体をダウンロードする。"""
    result = await document_archive.download_document(db, document_id, company_id, current_user.tenant_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Archived document not found")
    document, data = result
    return Response(
        content=data,
        media_type=document.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{document.file_name}"'},
    )


@router.post("/{document_id}/verify", response_model=DocumentVerifyResponse)
async def verify(
    document_id: UUID,
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    file: UploadFile | None = File(None),
    current_user: CurrentUser = Depends(require_permission(Permission.DOCUMENT_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> DocumentVerifyResponse:
    """改ざん検知。ファイル未指定時は保存済み本体を、指定時は再アップロード分を照合する。"""
    file_bytes = await file.read() if file is not None else None
    result = await document_archive.verify_document(
        db, document_id, company_id, current_user.tenant_id, file_bytes
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Archived document not found")
    return DocumentVerifyResponse(**result)


@router.post("/denchou/electronic-transaction/check", response_model=DenchouElectronicCheckResponse)
async def check_denchou_electronic_transaction(
    payload: DenchouElectronicCheckRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.DOCUMENT_MANAGE)),
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
    current_user: CurrentUser = Depends(require_permission(Permission.DOCUMENT_MANAGE)),
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
