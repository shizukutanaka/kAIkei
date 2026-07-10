"""IP帯域制限ミドルウェア（テナントセキュリティポリシーの強制）。

認証済みリクエストについて、そのテナントの TenantSecurityPolicy を参照し、
許可IP帯域(allowed_ip_cidrs)が設定されている場合に送信元IPを検査する。
許可帯域外なら 403 を返す。許可帯域が空・ポリシー未設定・未認証は素通し。
"""
import logging
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.database import async_session_factory
from app.models.models import TenantSecurityPolicy, User
from app.services.security_policy import ip_allowed

logger = logging.getLogger(__name__)

SKIP_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")


def client_ip(x_forwarded_for: str | None, client_host: str | None) -> str | None:
    """送信元IPを解決する。プロキシ経由(X-Forwarded-For)なら先頭ホップを採用。"""
    if x_forwarded_for:
        first = x_forwarded_for.split(",")[0].strip()
        if first:
            return first
    return client_host


class IpRestrictionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path.startswith(SKIP_PREFIXES) or "/auth/" in path:
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            from app.core.security import decode_token

            payload = decode_token(auth.removeprefix("Bearer "))
            sub = payload.get("sub") if payload else None
            if sub:
                try:
                    if await self._is_blocked(sub, request):
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "Access denied from this IP address"},
                        )
                except Exception as e:  # noqa: BLE001 -- IP検査失敗でリクエストを止めない
                    logger.warning("IP restriction check failed: %s", e)

        return await call_next(request)

    async def _is_blocked(self, sub: str, request: Request) -> bool:
        try:
            user_id = uuid.UUID(sub)
        except (ValueError, TypeError):
            return False

        async with async_session_factory() as session:
            result = await session.execute(
                select(TenantSecurityPolicy)
                .join(User, User.tenant_id == TenantSecurityPolicy.tenant_id)
                .where(User.user_id == user_id)
            )
            policy = result.scalar_one_or_none()

        if policy is None or not policy.allowed_ip_cidrs:
            return False

        ip = client_ip(
            request.headers.get("x-forwarded-for"),
            request.client.host if request.client else None,
        )
        if ip is None:
            return False
        return not ip_allowed(ip, list(policy.allowed_ip_cidrs))
