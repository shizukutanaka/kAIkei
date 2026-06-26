from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rbac import Permission, Role, ROLE_PERMISSIONS, get_role_permissions, has_permission

router = APIRouter()


@router.get("/roles")
async def list_roles() -> dict:
    """システムロール一覧を取得する。"""
    return {
        "roles": [
            {
                "role": role.value,
                "permissions": [p.value for p in perms],
            }
            for role, perms in ROLE_PERMISSIONS.items()
        ]
    }


@router.get("/me")
async def get_my_permissions(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """現在のユーザーの権限を取得する。"""
    return {
        "user_id": str(current_user.user_id),
        "email": current_user.email,
        "display_name": current_user.display_name,
        "role": current_user.role,
        "permissions": current_user.permissions,
    }


@router.get("/check/{permission}")
async def check_permission(
    permission: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """指定権限を持っているか確認する。"""
    try:
        perm = Permission(permission)
    except ValueError:
        return {"has_permission": False, "error": f"Unknown permission: {permission}"}

    return {
        "has_permission": has_permission(current_user.role, perm),
        "permission": permission,
        "role": current_user.role,
    }
