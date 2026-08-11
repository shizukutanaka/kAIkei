import logging

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.secrets_check import check_insecure_defaults
from app.middleware.audit_log import AuditLogMiddleware
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.ip_restriction import IpRestrictionMiddleware
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
app.add_middleware(IpRestrictionMiddleware)


@app.on_event("startup")
async def validate_secrets() -> None:
    """開発用デフォルト値の秘密情報を検出する。本番では起動を拒否する。"""
    issues = check_insecure_defaults(
        settings.JWT_SECRET_KEY, settings.S3_ACCESS_KEY, settings.S3_SECRET_KEY
    )
    if not issues:
        return
    if settings.ENVIRONMENT.strip().lower() == "production":
        raise RuntimeError(
            "Refusing to start in production with insecure configuration: " + "; ".join(issues)
        )
    for issue in issues:
        logger.warning("Insecure default configuration (development only)", issue=issue)


@app.on_event("startup")
async def start_background_jobs() -> None:
    """Webhook配信ワーカー等の定期ジョブを起動する。"""
    if not settings.BACKGROUND_JOBS_ENABLED:
        logger.info("Background jobs disabled (BACKGROUND_JOBS_ENABLED=false)")
        return
    from app.services import background_jobs

    app.state.background_tasks = background_jobs.start_background_jobs()


@app.on_event("shutdown")
async def stop_background_jobs() -> None:
    tasks = getattr(app.state, "background_tasks", None)
    if tasks:
        from app.services import background_jobs

        await background_jobs.stop_background_jobs(tasks)


@app.exception_handler(ConnectionError)
@app.exception_handler(OperationalError)
@app.exception_handler(DBAPIError)
async def database_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """DB接続断を 503 として返す。

    接続不能時、asyncpg が送出する ConnectionRefusedError は
    SQLAlchemy の DBAPIError にラップされず素通りするため、
    本文なしの 500 Internal Server Error になっていた。
    クライアントがリトライ可能と判断できる 503 に正規化する。
    """
    logger.error("Database unavailable", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable. Please retry later."},
    )


@app.get("/health")
async def health_check() -> JSONResponse:
    """ヘルスチェックエンドポイント（DB接続確認付き）。

    DB断時は 503 を返す。200固定だとコンテナ/ロードバランサの
    ヘルスチェックが縮退状態を検知できないため。
    """
    from sqlalchemy import text as sa_text

    from app.core.database import engine
    try:
        async with engine.connect() as conn:
            await conn.execute(sa_text("SELECT 1"))
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "app": settings.APP_NAME, "database": "connected"},
        )
    except Exception as e:
        logger.error("Health check DB connection failed", error=str(e))
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "app": settings.APP_NAME, "database": "disconnected"},
        )


app.include_router(api_router, prefix="/api/v1")
