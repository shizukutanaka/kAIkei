from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.schemas.schemas import (
    AuditDetectionResponse,
    AuditDetectionStatusUpdate,
    AuditScanResponse,
)
from app.services import audit_detection

router = APIRouter()


@router.post("/scan", response_model=AuditScanResponse)
async def scan(
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.AUDIT_REVIEW)),
    db: AsyncSession = Depends(get_db),
) -> AuditScanResponse:
    """会社の仕訳をスキャンし、リスク検知ログを記録する。"""
    result = await audit_detection.scan_company(
        db, tenant_id=current_user.tenant_id, company_id=company_id
    )
    return AuditScanResponse(**result)


@router.get("/detections", response_model=list[AuditDetectionResponse])
async def list_detections(
    company_id: UUID = Query(...),
    detection_status: str | None = Query(None, alias="status"),
    risk_level: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: CurrentUser = Depends(require_permission(Permission.AUDIT_REVIEW)),
    db: AsyncSession = Depends(get_db),
) -> list[AuditDetectionResponse]:
    """リスク検知ログを一覧取得する。"""
    logs = await audit_detection.list_detections(
        db, company_id=company_id, status=detection_status, risk_level=risk_level, limit=limit
    )
    return [AuditDetectionResponse.model_validate(log) for log in logs]


@router.patch("/detections/{detection_id}", response_model=AuditDetectionResponse)
async def update_detection_status(
    detection_id: UUID,
    payload: AuditDetectionStatusUpdate,
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.AUDIT_REVIEW)),
    db: AsyncSession = Depends(get_db),
) -> AuditDetectionResponse:
    """検知ログの確認状態を更新する（confirmed / dismissed）。"""
    log = await audit_detection.update_status(
        db,
        company_id=company_id,
        detection_id=detection_id,
        new_status=payload.status,
        reviewed_by=current_user.user_id,
    )
    if log is None:
        raise HTTPException(status_code=404, detail="Detection log not found")
    return AuditDetectionResponse.model_validate(log)
