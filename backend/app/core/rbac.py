from enum import Enum
from typing import Any


class Role(str, Enum):
    """システムロール定義。"""
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    APPROVER = "approver"
    VIEWER = "viewer"


class Permission(str, Enum):
    """権限定義。"""
    # Journal
    JOURNAL_CREATE = "journal:create"
    JOURNAL_READ = "journal:read"
    JOURNAL_UPDATE = "journal:update"
    JOURNAL_DELETE = "journal:delete"
    JOURNAL_APPROVE = "journal:approve"
    JOURNAL_POST = "journal:post"
    JOURNAL_VOID = "journal:void"
    # Master
    MASTER_CREATE = "master:create"
    MASTER_READ = "master:read"
    MASTER_UPDATE = "master:update"
    MASTER_DELETE = "master:delete"
    # AI
    AI_INFER = "ai:infer"
    AI_REVIEW = "ai:review"
    # Reports
    REPORT_READ = "report:read"
    REPORT_EXPORT = "report:export"
    # Integrations
    INTEGRATION_IMPORT = "integration:import"
    INTEGRATION_CONFIG = "integration:config"
    # Knowledge
    KNOWLEDGE_SEARCH = "knowledge:search"
    # User
    USER_MANAGE = "user:manage"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: set(Permission),
    Role.ACCOUNTANT: {
        Permission.JOURNAL_CREATE,
        Permission.JOURNAL_READ,
        Permission.JOURNAL_UPDATE,
        Permission.JOURNAL_VOID,
        Permission.MASTER_CREATE,
        Permission.MASTER_READ,
        Permission.MASTER_UPDATE,
        Permission.AI_INFER,
        Permission.REPORT_READ,
        Permission.REPORT_EXPORT,
        Permission.INTEGRATION_IMPORT,
        Permission.KNOWLEDGE_SEARCH,
    },
    Role.APPROVER: {
        Permission.JOURNAL_READ,
        Permission.JOURNAL_APPROVE,
        Permission.JOURNAL_POST,
        Permission.REPORT_READ,
        Permission.AI_REVIEW,
        Permission.KNOWLEDGE_SEARCH,
    },
    Role.VIEWER: {
        Permission.JOURNAL_READ,
        Permission.MASTER_READ,
        Permission.REPORT_READ,
        Permission.KNOWLEDGE_SEARCH,
    },
}


def has_permission(role: str, permission: Permission) -> bool:
    """ロールが権限を持つか確認する。"""
    try:
        r = Role(role)
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS.get(r, set())


def get_role_permissions(role: str) -> list[str]:
    """ロールの権限一覧を取得する。"""
    try:
        r = Role(role)
    except ValueError:
        return []
    return [p.value for p in ROLE_PERMISSIONS.get(r, set())]
