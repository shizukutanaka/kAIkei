from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.schemas.schemas import SecurityPolicyResponse, SecurityPolicyUpdate
from app.services import security_policy

router = APIRouter()


@router.get("", response_model=SecurityPolicyResponse)
async def get_policy(
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SecurityPolicyResponse:
    """テナントのセキュリティポリシーを取得する（未設定なら既定値で作成）。"""
    policy = await security_policy.get_policy(db, current_user.tenant_id)
    if policy is None:
        policy = await security_policy.upsert_policy(db, current_user.tenant_id)
    return SecurityPolicyResponse.model_validate(policy)


@router.put("", response_model=SecurityPolicyResponse)
async def update_policy(
    payload: SecurityPolicyUpdate,
    current_user: CurrentUser = Depends(require_permission(Permission.USER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> SecurityPolicyResponse:
    """テナントのセキュリティポリシーを更新する。"""
    policy = await security_policy.upsert_policy(
        db,
        tenant_id=current_user.tenant_id,
        require_mfa=payload.require_mfa,
        allowed_ip_cidrs=payload.allowed_ip_cidrs,
        session_timeout_minutes=payload.session_timeout_minutes,
        password_min_length=payload.password_min_length,
        max_failed_attempts=payload.max_failed_attempts,
    )
    return SecurityPolicyResponse.model_validate(policy)
