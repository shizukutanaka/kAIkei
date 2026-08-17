import logging
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.middleware.ip_restriction import client_ip

logger = logging.getLogger(__name__)

SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """APIレート制限ミドルウェア。

    IPアドレスごとにリクエスト数を制限し、超過時は429 Too Many Requestsを返す。
    スライディングウィンドウ方式で、指定期間内のリクエスト数を追跡する。
    """

    def __init__(
        self,
        app,
        max_requests: int = 100,
        window_seconds: int = 60,
        trust_proxy: bool = False,
        max_tracked_keys: int = 10_000,
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # X-Forwarded-For を採用するのは信頼できるプロキシ配下と分かっている場合のみ。
        self.trust_proxy = trust_proxy
        self.max_tracked_keys = max_tracked_keys
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        """送信元IPを解決する。

        X-Forwarded-For はクライアントが自由に付与できるヘッダのため、無条件に採用すると
        **リクエストごとに値を変えるだけでレート制限を完全に回避**できる
        （実測: 上限5件の設定で1000リクエストを送っても一度も制限に達しない）。
        さらに攻撃者が任意のキーを無限に作れるため、追跡用dictが際限なく膨らむ。

        IP許可リスト側（ip_restriction.client_ip）と同じ方針で、trust_proxy が真の
        場合のみ先頭ホップを採用し、既定では直接接続元のIPのみを信頼する。
        """
        return (
            client_ip(
                request.headers.get("x-forwarded-for"),
                request.client.host if request.client else None,
                trust_proxy=self.trust_proxy,
            )
            or "unknown"
        )

    def _cleanup(self, key: str, now: float) -> None:
        cutoff = now - self.window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]
        if not self._requests[key]:
            del self._requests[key]

    def _evict_stale(self, now: float) -> None:
        """追跡キーが上限を超えたら、ウィンドウを過ぎた古いキーを一括で破棄する。

        _cleanup は「そのキーに再度アクセスがあったとき」しか消えないため、
        一度きりのIPが大量に現れるとメモリが解放されない。上限到達時にまとめて掃除する。
        """
        if len(self._requests) <= self.max_tracked_keys:
            return
        cutoff = now - self.window_seconds
        stale = [k for k, times in self._requests.items() if not times or times[-1] <= cutoff]
        for key in stale:
            del self._requests[key]
        if len(self._requests) > self.max_tracked_keys:
            logger.warning(
                "Rate limit tracking table still %d keys after eviction", len(self._requests)
            )

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        request_ip = self._get_client_ip(request)
        now = time.monotonic()

        self._evict_stale(now)
        self._cleanup(request_ip, now)

        if len(self._requests.get(request_ip, [])) >= self.max_requests:
            logger.warning("Rate limit exceeded for %s", request_ip)
            return JSONResponse(
                content={
                    "detail": "リクエスト数が上限に達しました。しばらくしてから再試行してください。",
                    "code": "RATE_LIMIT_EXCEEDED",
                },
                status_code=429,
                headers={"Retry-After": str(self.window_seconds)},
            )

        self._requests[request_ip].append(now)
        return await call_next(request)
