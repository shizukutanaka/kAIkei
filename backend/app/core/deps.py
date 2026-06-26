from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import Permission, has_permission
from app.core.security import decode_token
from app.models.models import User


@dataclass
class CurrentUser:
    """認証済みユーザー情報。"""
    user_id: UUID
    tenant_id: UUID
    email: str
    display_name: str
    role: str
    permissions: list[str]


async def get_current_user(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """JWT トークンから認証済みユーザーを取得する。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ")
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(
        select(User).where(
            User.user_id == UUID(user_id),
            User.is_deleted == False,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    from app.core.rbac import get_role_permissions

    return CurrentUser(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        permissions=get_role_permissions(user.role),
    )


def require_permission(permission: Permission):
    """指定権限を要求する依存関係ファクトリ。

    使用例:
        @router.post("/journals", dependencies=[Depends(require_permission(Permission.JOURNAL_CREATE))])
    """
    async def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires {permission.value}",
            )
        return current_user
    return _check


async def get_current_user_optional(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser | None:
    """認証があればユーザーを返すが、未認証でもエラーにしない。"""
    if not authorization:
        return None
    try:
        return await get_current_user(authorization=authorization, db=db)
    except HTTPException:
        return None
