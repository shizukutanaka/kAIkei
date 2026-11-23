import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission, verified_company_id
from app.core.rbac import Permission
from app.schemas.schemas import (
    AutoReconcileRequest,
    AutoReconcileResponse,
    BankImportResponse,
    BankLineSuggestionResponse,
    BankStatementLineResponse,
    CreateJournalFromBankLineRequest,
    JournalResponse,
    ManualMatchRequest,
)
from app.services import bank_journal, bank_reconciliation

router = APIRouter()

# 利用者が調整できる列対応のキー（bank_reconciliation._COLUMN_ALIASES と対応）。
_COLUMN_MAP_KEYS = {
    "date", "deposit", "withdrawal", "amount", "direction", "balance", "description", "counterparty",
}


def _parse_column_map(raw: str | None) -> dict[str, str] | None:
    """列対応の指定（JSON文字列）を検証して辞書にする。不正なら400。"""
    if raw is None or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"列の対応付け（column_map）のJSONが不正です: {e}") from e
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="列の対応付け（column_map）はJSONオブジェクトで指定してください")
    column_map: dict[str, str] = {}
    for key, value in parsed.items():
        if key not in _COLUMN_MAP_KEYS:
            raise HTTPException(status_code=400, detail=f"列の対応付けに使えないキーです: {key}")
        if not isinstance(value, str):
            raise HTTPException(status_code=400, detail=f"列の対応付けの値は文字列で指定してください: {key}")
        if value.strip():
            column_map[key] = value
    return column_map or None


@router.post("/import-statement", response_model=BankImportResponse, status_code=status.HTTP_201_CREATED)
async def import_statement(
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    file: UploadFile = File(...),
    column_map: str | None = Form(None),
    current_user: CurrentUser = Depends(require_permission(Permission.INTEGRATION_IMPORT)),
    db: AsyncSession = Depends(get_db),
) -> BankImportResponse:
    """銀行明細CSVをアップロードして取り込む。

    文字コードは UTF-8 / Shift_JIS を自動判定する。列名が想定と違う場合は
    column_map（JSON）で「どの列が何か」を指定できる。読み飛ばした行は
    理由とともにレスポンスの skipped へ返す（黙って捨てない）。
    """
    content = await file.read()
    try:
        csv_text = bank_reconciliation.decode_statement_bytes(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    lines, skipped = await bank_reconciliation.import_statement_detailed(
        db,
        tenant_id=current_user.tenant_id,
        company_id=company_id,
        csv_text=csv_text,
        column_map=_parse_column_map(column_map),
    )
    return BankImportResponse(
        imported=len(lines),
        lines=[BankStatementLineResponse.model_validate(line) for line in lines],
        skipped=[{"row_number": s.row_number, "reason": s.reason} for s in skipped],
    )


@router.get("/statement-lines", response_model=list[BankStatementLineResponse])
async def list_statement_lines(
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
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


@router.get("/statement-lines/{line_id}/suggestion", response_model=BankLineSuggestionResponse)
async def suggest_for_line(
    line_id: UUID,
    bank_account_id: UUID = Query(...),
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_READ)),
    db: AsyncSession = Depends(get_db),
) -> BankLineSuggestionResponse:
    """未消込の銀行明細について、学習した仕訳ルールから相手科目の候補を返す。"""
    try:
        result = await bank_journal.suggest_for_bank_line(db, company_id, line_id, bank_account_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except bank_journal.AlreadyReconciledError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return BankLineSuggestionResponse(**result)


@router.post(
    "/statement-lines/{line_id}/create-journal",
    response_model=JournalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_journal_for_line(
    line_id: UUID,
    payload: CreateJournalFromBankLineRequest,
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> JournalResponse:
    """銀行明細1件から仕訳ドラフトを作る。相手科目は人が確定した値を使う。

    作られた仕訳は下書き。確定（posted）すると学習データになり、次回以降の
    候補提示に効く（人の修正が学習に返る）。
    """
    try:
        header = await bank_journal.create_journal_from_bank_line(
            db,
            company_id=company_id,
            line_id=line_id,
            bank_account_id=payload.bank_account_id,
            counterpart_account_id=payload.counterpart_account_id,
            created_by=current_user.user_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except bank_journal.AlreadyReconciledError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return JournalResponse.model_validate(header)


@router.post("/auto-reconcile", response_model=AutoReconcileResponse)
async def auto_reconcile(
    payload: AutoReconcileRequest,
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
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
        max_fee=payload.max_fee,
    )
    return AutoReconcileResponse(**result)


@router.post("/statement-lines/{line_id}/match", response_model=BankStatementLineResponse)
async def match_line(
    line_id: UUID,
    payload: ManualMatchRequest,
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
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
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
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
