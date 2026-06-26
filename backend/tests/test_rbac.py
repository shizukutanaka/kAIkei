import pytest

from app.core.rbac import Permission, Role, ROLE_PERMISSIONS, has_permission, get_role_permissions


class TestRBAC:
    def test_admin_has_all_permissions(self):
        for perm in Permission:
            assert has_permission("admin", perm) is True

    def test_accountant_can_create_journal(self):
        assert has_permission("accountant", Permission.JOURNAL_CREATE) is True

    def test_accountant_cannot_approve(self):
        assert has_permission("accountant", Permission.JOURNAL_APPROVE) is False

    def test_approver_can_approve(self):
        assert has_permission("approver", Permission.JOURNAL_APPROVE) is True

    def test_approver_cannot_create_journal(self):
        assert has_permission("approver", Permission.JOURNAL_CREATE) is False

    def test_viewer_can_read(self):
        assert has_permission("viewer", Permission.JOURNAL_READ) is True
        assert has_permission("viewer", Permission.REPORT_READ) is True

    def test_viewer_cannot_create(self):
        assert has_permission("viewer", Permission.JOURNAL_CREATE) is False
        assert has_permission("viewer", Permission.MASTER_CREATE) is False

    def test_unknown_role_has_no_permissions(self):
        assert has_permission("unknown", Permission.JOURNAL_READ) is False

    def test_get_role_permissions_admin(self):
        perms = get_role_permissions("admin")
        assert len(perms) == len(Permission)

    def test_get_role_permissions_viewer(self):
        perms = get_role_permissions("viewer")
        assert "journal:read" in perms
        assert "journal:create" not in perms

    def test_get_role_permissions_unknown(self):
        perms = get_role_permissions("unknown")
        assert perms == []

    def test_role_enum_values(self):
        assert Role.ADMIN.value == "admin"
        assert Role.ACCOUNTANT.value == "accountant"
        assert Role.APPROVER.value == "approver"
        assert Role.VIEWER.value == "viewer"

    def test_all_roles_have_permissions(self):
        for role in Role:
            assert len(ROLE_PERMISSIONS[role]) > 0
