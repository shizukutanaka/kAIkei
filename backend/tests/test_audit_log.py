import json
from uuid import uuid4

from app.middleware.audit_log import SKIP_PATHS, AuditLogMiddleware, redact_sensitive_fields


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


class TestNestedRedaction:
    """入れ子・配列の中まで伏字にすること。

    監査ログは長期保存され監査人が閲覧するため、一度書き込まれた機微情報は影響が残る。
    現行スキーマは機微フィールドがトップレベルにあり実害は生じていないが、
    エンドポイントは随時追加されるため、ボディの形に依存しない実装にしておく。
    """

    def test_nested_object_is_redacted(self):
        out = redact_sensitive_fields('{"user":{"email":"a@b.c","password":"P@ssw0rd!"}}')
        assert "P@ssw0rd!" not in out
        assert "***REDACTED***" in out
        assert "a@b.c" in out  # 機微でない値は残す

    def test_array_of_objects_is_redacted(self):
        out = redact_sensitive_fields('{"users":[{"password":"P@ssw0rd!"},{"password":"x"}]}')
        assert "P@ssw0rd!" not in out
        assert out.count("***REDACTED***") == 2

    def test_top_level_array_is_redacted(self):
        out = redact_sensitive_fields('[{"refresh_token":"tok-value"}]')
        assert "tok-value" not in out

    def test_deeply_nested_secret_is_redacted(self):
        out = redact_sensitive_fields('{"a":{"b":{"c":{"secret":"s3cr3t-value"}}}}')
        assert "s3cr3t-value" not in out

    def test_non_json_body_is_returned_unchanged(self):
        assert redact_sensitive_fields("not-json-body") == "not-json-body"

    def test_scalar_json_is_returned_unchanged(self):
        assert redact_sensitive_fields('"just-a-string"') == '"just-a-string"'
