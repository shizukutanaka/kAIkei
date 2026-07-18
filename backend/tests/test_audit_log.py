import json

import pytest
from uuid import uuid4

from app.middleware.audit_log import AuditLogMiddleware, SKIP_PATHS, redact_sensitive_fields


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


class TestRedactSensitiveFields:
    def test_redacts_password(self):
        body = json.dumps({"email": "a@example.com", "password": "hunter2"})
        result = json.loads(redact_sensitive_fields(body))
        assert result["email"] == "a@example.com"
        assert result["password"] == "***REDACTED***"

    def test_redacts_mfa_code_and_login_mfa_code(self):
        body = json.dumps({"email": "a@example.com", "password": "x", "mfa_code": "123456"})
        result = json.loads(redact_sensitive_fields(body))
        assert result["password"] == "***REDACTED***"
        assert result["mfa_code"] == "***REDACTED***"

    def test_redacts_mfa_enable_disable_code(self):
        body = json.dumps({"code": "654321"})
        result = json.loads(redact_sensitive_fields(body))
        assert result["code"] == "***REDACTED***"

    def test_redacts_current_code_for_setup_rotation(self):
        body = json.dumps({"current_code": "111111"})
        result = json.loads(redact_sensitive_fields(body))
        assert result["current_code"] == "***REDACTED***"

    def test_non_sensitive_fields_untouched(self):
        body = json.dumps({"description": "some journal entry", "amount": 1000})
        result = json.loads(redact_sensitive_fields(body))
        assert result == {"description": "some journal entry", "amount": 1000}

    def test_non_json_body_passed_through(self):
        assert redact_sensitive_fields("not json at all") == "not json at all"

    def test_json_array_passed_through(self):
        body = json.dumps([1, 2, 3])
        assert redact_sensitive_fields(body) == body

    def test_empty_body(self):
        assert redact_sensitive_fields("") == ""
