import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.models import IdempotencyRecord

logger = logging.getLogger(__name__)

IDEMPOTENCY_HEADER = "Idempotency-Key"
IDEMPOTENCY_TTL_HOURS = 24


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """冪等性保証ミドルウェア。

    Idempotency-Key ヘッダー付きの POST/PUT リクエストに対して:
    1. 同一キー + 同一リクエストハッシュの過去レスポンスがあれば再返却
    2. 同一キー + 異なるリクエストハッシュなら 409 Conflict
    3. 新規キーならレスポンスを保存して返却

    適用対象: POST, PUT, PATCH
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
        if not idempotency_key:
            return await call_next(request)

        body_bytes = await request.body()

        request_hash = hashlib.sha256(body_bytes).hexdigest()

        cached = await self._get_cached_response(idempotency_key, request_hash)
        if cached:
            if cached["match"]:
                logger.info("Idempotency hit: returning cached response for key=%s", idempotency_key)
                return JSONResponse(
                    content=json.loads(cached["response_body"]),
                    status_code=cached["response_status"],
                    headers={"X-Idempotent-Replay": "true"},
                )
            else:
                return JSONResponse(
                    content={
                        "detail": "Idempotency-Key was used with a different request body",
                        "code": "IDEMPOTENCY_CONFLICT",
                    },
                    status_code=409,
                )

        async def receive() -> dict:
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        request._receive = receive

        response = await call_next(request)

        if 200 <= response.status_code < 400:
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            await self._save_response(
                idempotency_key,
                request_hash,
                response.status_code,
                response_body.decode("utf-8", errors="replace"),
            )

            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        return response

    async def _get_cached_response(self, key: str, request_hash: str) -> dict | None:
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.idempotency_key == key,
                        IdempotencyRecord.expires_at > datetime.now(timezone.utc),
                    )
                )
                record = result.scalar_one_or_none()

                if not record:
                    return None

                return {
                    "match": record.request_hash == request_hash,
                    "response_status": record.response_status,
                    "response_body": record.response_body,
                }
        except Exception as e:
            logger.warning("Idempotency cache lookup failed: %s", e)
            return None

    async def _save_response(
        self,
        key: str,
        request_hash: str,
        status_code: int,
        response_body: str,
    ) -> None:
        try:
            async with async_session_factory() as session:
                expires_at = datetime.now(timezone.utc) + timedelta(hours=IDEMPOTENCY_TTL_HOURS)

                record = IdempotencyRecord(
                    idempotency_key=key,
                    request_hash=request_hash,
                    response_status=status_code,
                    response_body=response_body,
                    expires_at=expires_at,
                )
                session.add(record)
                await session.commit()
        except Exception as e:
            logger.warning("Idempotency save failed: %s", e)
