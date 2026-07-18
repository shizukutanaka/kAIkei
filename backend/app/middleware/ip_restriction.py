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
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.models import TenantSecurityPolicy, User
from app.services.security_policy import ip_allowed

logger = logging.getLogger(__name__)

SKIP_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")
# 認証を必要としないauthエンドポイントのみ除外する。/auth/mfa/* 等の
# 認証必須エンドポイントまで丸ごと除外しないよう、末尾一致で個別に列挙する。
UNAUTHENTICATED_AUTH_SUFFIXES = ("/auth/login", "/auth/register", "/auth/refresh")


def client_ip(
    x_forwarded_for: str | None, client_host: str | None, trust_proxy: bool = False
) -> str | None:
    """送信元IPを解決する。

    X-Forwarded-Forはクライアントが任意に指定できるヘッダであり、無条件に
    信頼するとIP許可リストを詐称ヘッダだけで回避できてしまう。trust_proxy=True
    （信頼できるリバースプロキシが上書きすることが保証された構成）の場合のみ
    先頭ホップを採用し、既定では直接接続元のIPのみを信頼する。
    """
    if trust_proxy and x_forwarded_for:
        first = x_forwarded_for.split(",")[0].strip()
        if first:
            return first
    return client_host


def is_unauthenticated_auth_path(path: str) -> bool:
    """未認証で呼び出されるauthエンドポイント（login/register/refresh）か判定する。"""
    return any(path.endswith(suffix) for suffix in UNAUTHENTICATED_AUTH_SUFFIXES)


class IpRestrictionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path.startswith(SKIP_PREFIXES) or is_unauthenticated_auth_path(path):
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
                except (SQLAlchemyError, ConnectionError, TimeoutError) as e:
                    # DB接続不良等の既知の障害モードに限り、意図的にfail-openする
                    # （IP検査だけを理由に全ユーザーをロックアウトしないため）。
                    # それ以外の例外（プログラムのバグ等）は握りつぶさず伝播させる。
                    logger.warning("IP restriction check failed, failing open: %s", e)

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
            trust_proxy=settings.TRUST_PROXY_HEADERS,
        )
        if ip is None:
            return False
        return not ip_allowed(ip, list(policy.allowed_ip_cidrs))
