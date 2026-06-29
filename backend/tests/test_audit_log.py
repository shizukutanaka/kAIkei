import pytest
from uuid import uuid4

from app.middleware.audit_log import AuditLogMiddleware, SKIP_PATHS


class TestAuditLog:
    def test_skip_paths_contains_health(self):
        assert "/health" in SKIP_PATHS

    def test_skip_paths_contains_docs(self):
        assert "/docs" in SKIP_PATHS
        assert "/redoc" in SKIP_PATHS

    def test_skip_paths_contains_openapi(self):
        assert "/openapi.json" in SKIP_PATHS

    def test_middleware_class_exists(self):
        assert AuditLogMiddleware is not None

    def test_uuid_generation_for_tenant(self):
        from app.models.models import AuditLog
        log = AuditLog(
            tenant_id=uuid4(),
            action="post",
            resource_type="journals",
            method="POST",
            path="/api/v1/journals",
            status_code=201,
        )
        assert log.action == "post"
        assert log.resource_type == "journals"
        assert log.method == "POST"
        assert log.status_code == 201
