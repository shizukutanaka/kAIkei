import logging
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.database import async_session_factory
from app.models.models import AuditLog

logger = logging.getLogger(__name__)

SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


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
                try:
                    user_id = uuid.UUID(payload.get("sub"))
                except (ValueError, TypeError):
                    pass

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
            try:
                body_text = body_bytes.decode("utf-8", errors="replace")[:2000]
            except Exception:
                pass

        async with async_session_factory() as session:
            log = AuditLog(
                tenant_id=uuid.UUID(int=0),
                user_id=user_id,
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
