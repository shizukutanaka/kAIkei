import contextlib
import json
import logging
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.database import async_session_factory
from app.models.models import AuditLog

logger = logging.getLogger(__name__)

SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

# 監査ログに平文で残してはいけないフィールド名（パスワード・TOTPコード・トークン等）。
SENSITIVE_BODY_KEYS = {
    "password",
    "new_password",
    "old_password",
    "mfa_code",
    "code",
    "current_code",
    "secret",
    "refresh_token",
    "access_token",
}

REDACTED_PLACEHOLDER = "***REDACTED***"


def _redact_value(value: object) -> object:
    """入れ子のdict/listを再帰的に辿り、機微キーの値を伏字にする。"""
    if isinstance(value, dict):
        return {
            k: (REDACTED_PLACEHOLDER if k in SENSITIVE_BODY_KEYS else _redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def redact_sensitive_fields(body_text: str) -> str:
    """JSON形式のリクエストボディから既知の機微キーの値を伏字にする。

    監査ログは長期保存され監査人が閲覧するため、パスワードやトークンが一度でも
    書き込まれると影響が残る。**入れ子のオブジェクトや配列の中まで再帰的に**伏字にする
    （トップレベルのキーだけを見ていると `{"user": {"password": ...}}` や
    `{"items": [{"password": ...}]}` の形が素通りする。現行のスキーマはいずれも
    機微フィールドがトップレベルにあり実害は生じていないが、エンドポイントは随時
    追加されるため、この防御はボディの形に依存しない実装にしておく）。

    JSONとしてパースできない場合（フォームデータ等）は元のテキストをそのまま返す
    （非JSONボディに機微キーが含まれる経路は本関数の対象外）。
    """
    try:
        data = json.loads(body_text)
    except (json.JSONDecodeError, TypeError):
        return body_text
    if not isinstance(data, dict | list):
        return body_text
    return json.dumps(_redact_value(data), ensure_ascii=False)


async def _tenant_of(session, user_id: uuid.UUID | None) -> uuid.UUID | None:
    """利用者の所属テナントを引く。特定できなければ None。

    認証前のイベント（ログイン失敗等）は user_id が無いか、あっても実在しない。
    そうした記録こそ監査上の価値が高いので、テナント不明でも捨てずに残せるよう
    `audit_logs.tenant_id` は NULL を許容している。

    user_id が実在しない場合に user_id ごと落とすのは、users への外部キー違反で
    書き込み自体が失敗するのを避けるため。
    """
    if user_id is None:
        return None
    from sqlalchemy import select

    from app.models.models import User

    result = await session.execute(select(User.tenant_id).where(User.user_id == user_id))
    return result.scalar_one_or_none()


class AuditLogMiddleware(BaseHTTPMiddleware):
    """操作証跡ログミドルウェア。

    すべてのAPIリクエストを記録し、audit_logsテーブルに追記する。
    GET /health, /docs 等のヘルスチェック・ドキュメントパスは除外。
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        body_bytes = await request.body()

        async def receive() -> dict:
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        request._receive = receive

        response = await call_next(request)

        if request.method == "GET" and 200 <= response.status_code < 400:
            return response

        try:
            await self._log(request, response, body_bytes)
        except Exception as e:
            logger.warning("Audit log write failed: %s", e)

        return response

    async def _log(self, request: Request, response: Response, body_bytes: bytes) -> None:
        from app.core.security import decode_token

        user_id = None

        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth.removeprefix("Bearer ")
            payload = decode_token(token)
            if payload:
                with contextlib.suppress(ValueError, TypeError):
                    user_id = uuid.UUID(payload.get("sub"))

        path = request.url.path
        resource_type = "unknown"
        resource_id = None
        action = request.method.lower()

        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2:
            resource_type = parts[-2]
            if len(parts) >= 3:
                resource_id = parts[-1]

        body_text = None
        if body_bytes and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            with contextlib.suppress(Exception):
                body_text = redact_sensitive_fields(body_bytes.decode("utf-8", errors="replace"))[:2000]

        async with async_session_factory() as session:
            # tenant_id は利用者から引く。ここに固定値を入れると tenants への
            # 外部キー制約に必ず違反し、監査ログが1件も残らない。
            tenant_id = await _tenant_of(session, user_id)
            log = AuditLog(
                tenant_id=tenant_id,
                user_id=user_id if tenant_id is not None else None,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                method=request.method,
                path=path,
                status_code=response.status_code,
                request_body=body_text,
                response_summary=f"{response.status_code}",
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent", "")[:300] or None,
            )
            session.add(log)
            await session.commit()
