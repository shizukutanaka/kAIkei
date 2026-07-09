from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.schemas.schemas import (
    AiInferenceApplyRequest,
    AiInferenceLogCreate,
    AiInferenceLogResponse,
    AiInferenceStatsResponse,
)
from app.services import ai_inference_log

router = APIRouter()


@router.post("", response_model=AiInferenceLogResponse, status_code=status.HTTP_201_CREATED)
async def create_log(
    payload: AiInferenceLogCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.AI_INFER)),
    db: AsyncSession = Depends(get_db),
) -> AiInferenceLogResponse:
    """AI推論の証跡を記録する。"""
    log = await ai_inference_log.log_inference(
        db,
        tenant_id=current_user.tenant_id,
        company_id=payload.company_id,
        source_type=payload.source_type,
        suggestion=payload.suggestion,
        confidence=payload.confidence,
        input_summary=payload.input_summary,
        provider=payload.provider,
        journal_header_id=payload.journal_header_id,
    )
    return AiInferenceLogResponse.model_validate(log)


@router.get("", response_model=list[AiInferenceLogResponse])
async def list_logs(
    company_id: UUID = Query(...),
    source_type: str | None = Query(None),
    applied: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: CurrentUser = Depends(require_permission(Permission.AI_REVIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[AiInferenceLogResponse]:
    """AI推論証跡を一覧取得する。"""
    logs = await ai_inference_log.list_logs(
        db, company_id=company_id, source_type=source_type, applied=applied, limit=limit
    )
    return [AiInferenceLogResponse.model_validate(log) for log in logs]


@router.get("/stats", response_model=AiInferenceStatsResponse)
async def stats(
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.AI_REVIEW)),
    db: AsyncSession = Depends(get_db),
) -> AiInferenceStatsResponse:
    """AI推論の精度指標を集計する。"""
    result = await ai_inference_log.get_stats(db, company_id=company_id)
    return AiInferenceStatsResponse(**result)


@router.post("/{log_id}/apply", response_model=AiInferenceLogResponse)
async def apply(
    log_id: UUID,
    payload: AiInferenceApplyRequest,
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.AI_INFER)),
    db: AsyncSession = Depends(get_db),
) -> AiInferenceLogResponse:
    """推論を適用済みにし、確定内容との修正差分を記録する。"""
    log = await ai_inference_log.mark_applied(
        db, company_id=company_id, log_id=log_id, final=payload.final
    )
    if log is None:
        raise HTTPException(status_code=404, detail="Inference log not found")
    return AiInferenceLogResponse.model_validate(log)
