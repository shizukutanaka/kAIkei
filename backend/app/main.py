import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.middleware.audit_log import AuditLogMiddleware
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    ),
)

logger = structlog.get_logger()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-driven integrated back-office platform for Japan",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(AuditLogMiddleware)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """ヘルスチェックエンドポイント（DB接続確認付き）。"""
    from sqlalchemy import text as sa_text
    from app.core.database import engine
    try:
        async with engine.connect() as conn:
            await conn.execute(sa_text("SELECT 1"))
        return {"status": "ok", "app": settings.APP_NAME, "database": "connected"}
    except Exception as e:
        logger.error("Health check DB connection failed", error=str(e))
        return {"status": "degraded", "app": settings.APP_NAME, "database": "disconnected"}


app.include_router(api_router, prefix="/api/v1")
