import pytest
from app.middleware.rate_limit import RateLimitMiddleware, SKIP_PATHS


class TestRateLimit:
    def test_skip_paths_contains_health(self):
        assert "/health" in SKIP_PATHS

    def test_skip_paths_contains_docs(self):
        assert "/docs" in SKIP_PATHS
        assert "/redoc" in SKIP_PATHS

    def test_middleware_class_exists(self):
        assert RateLimitMiddleware is not None

    def test_default_config(self):
        import asyncio
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse

        async def homepage(request):
            return PlainTextResponse("ok")

        app = Starlette(routes=[homepage] if hasattr(Starlette, "routes") else [])
        middleware = RateLimitMiddleware(app, max_requests=5, window_seconds=10)
        assert middleware.max_requests == 5
        assert middleware.window_seconds == 10
