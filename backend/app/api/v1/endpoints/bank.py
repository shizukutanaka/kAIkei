from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.schemas.schemas import (
    AutoReconcileRequest,
    AutoReconcileResponse,
    BankImportResponse,
    BankStatementLineResponse,
    ManualMatchRequest,
)
from app.services import bank_reconciliation

router = APIRouter()


@router.post("/import-statement", response_model=BankImportResponse, status_code=status.HTTP_201_CREATED)
async def import_statement(
    company_id: UUID = Query(...),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_permission(Permission.INTEGRATION_IMPORT)),
    db: AsyncSession = Depends(get_db),
) -> BankImportResponse:
    """銀行明細CSVをアップロードして取り込む。"""
    content = await file.read()
    csv_text = content.decode("utf-8-sig")
    lines = await bank_reconciliation.import_statement_csv(
        db, tenant_id=current_user.tenant_id, company_id=company_id, csv_text=csv_text
    )
    return BankImportResponse(
        imported=len(lines),
        lines=[BankStatementLineResponse.model_validate(line) for line in lines],
    )


@router.get("/statement-lines", response_model=list[BankStatementLineResponse])
async def list_statement_lines(
    company_id: UUID = Query(...),
    reconciled: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[BankStatementLineResponse]:
    """銀行明細を一覧取得する。"""
    lines = await bank_reconciliation.list_statement_lines(
        db, company_id=company_id, reconciled=reconciled, limit=limit
    )
    return [BankStatementLineResponse.model_validate(line) for line in lines]


@router.post("/auto-reconcile", response_model=AutoReconcileResponse)
async def auto_reconcile(
    payload: AutoReconcileRequest,
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> AutoReconcileResponse:
    """未消込の銀行明細を仕訳明細に対して自動消込する。"""
    result = await bank_reconciliation.auto_reconcile(
        db,
        company_id=company_id,
        bank_account_id=payload.bank_account_id,
        date_tolerance_days=payload.date_tolerance_days,
        min_score=payload.min_score,
    )
    return AutoReconcileResponse(**result)


@router.post("/statement-lines/{line_id}/match", response_model=BankStatementLineResponse)
async def match_line(
    line_id: UUID,
    payload: ManualMatchRequest,
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> BankStatementLineResponse:
    """銀行明細を仕訳明細に手動で消込する。"""
    line = await bank_reconciliation.manual_match(
        db, company_id=company_id, bank_statement_line_id=line_id, journal_line_id=payload.journal_line_id
    )
    if line is None:
        raise HTTPException(status_code=404, detail="Bank statement line not found")
    return BankStatementLineResponse.model_validate(line)


@router.post("/statement-lines/{line_id}/unmatch", response_model=BankStatementLineResponse)
async def unmatch_line(
    line_id: UUID,
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> BankStatementLineResponse:
    """銀行明細の消込を解除する。"""
    line = await bank_reconciliation.unmatch(
        db, company_id=company_id, bank_statement_line_id=line_id
    )
    if line is None:
        raise HTTPException(status_code=404, detail="Bank statement line not found")
    return BankStatementLineResponse.model_validate(line)
