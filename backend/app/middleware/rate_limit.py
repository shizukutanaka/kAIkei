import time
import logging
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)

SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """APIレート制限ミドルウェア。

    IPアドレスごとにリクエスト数を制限し、超過時は429 Too Many Requestsを返す。
    スライディングウィンドウ方式で、指定期間内のリクエスト数を追跡する。
    """

    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup(self, key: str, now: float) -> None:
        cutoff = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]
        if not self._requests[key]:
            del self._requests[key]

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.monotonic()

        self._cleanup(client_ip, now)

        if len(self._requests.get(client_ip, [])) >= self.max_requests:
            logger.warning("Rate limit exceeded for %s", client_ip)
            return JSONResponse(
                content={
                    "detail": "リクエスト数が上限に達しました。しばらくしてから再試行してください。",
                    "code": "RATE_LIMIT_EXCEEDED",
                },
                status_code=429,
                headers={"Retry-After": str(self.window_seconds)},
            )

        self._requests[client_ip].append(now)
        return await call_next(request)
