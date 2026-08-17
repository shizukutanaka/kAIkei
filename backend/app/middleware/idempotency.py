import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.database import async_session_factory
from app.models.models import IdempotencyRecord

logger = logging.getLogger(__name__)

IDEMPOTENCY_HEADER = "Idempotency-Key"
IDEMPOTENCY_TTL_HOURS = 24


def build_scoped_key(
    idempotency_key: str, user_id: str | None, client_host: str | None
) -> str:
    """冪等キーを呼び出し元ごとに分離した保存キーへ変換する。

    冪等キーはクライアントが決める値で、`order-2026-0001` のように意味のある文字列が
    使われることも多い。呼び出し元で分離せずキー文字列だけで引くと、**別テナントが
    同じキーを使った瞬間に相手のキャッシュに当たる**:

    - リクエスト本文のハッシュまで一致すれば、**他テナントのレスポンス本文がそのまま返る**
      （情報漏洩）
    - 一致しなければ409が返り、**相手の正当なリクエストを妨害できる**（先に同じキーを
      登録しておくだけで成立する）

    そのため利用者単位で名前空間を分ける。未認証リクエストは接続元IPで分離する。
    """
    scope = f"user:{user_id}" if user_id else f"anon:{client_host or 'unknown'}"
    return f"{scope}|{idempotency_key}"


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

        # キャッシュは呼び出し元ごとに分離する（他テナントのレスポンスを引かないため）。
        idempotency_key = build_scoped_key(
            idempotency_key,
            self._current_user_id(request),
            request.client.host if request.client else None,
        )

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

    @staticmethod
    def _current_user_id(request: Request) -> str | None:
        """Authorizationヘッダのアクセストークンから利用者IDを取り出す。

        ミドルウェアは認証依存関係より前に走るため、ここではトークンを自前で読む。
        検証に失敗した場合はNoneを返し、未認証として（接続元IPで）分離する。
        認可判定はこの値では行わない（分離の名前空間としてのみ使う）。
        """
        authorization = request.headers.get("authorization") or ""
        if not authorization.startswith("Bearer "):
            return None
        try:
            from app.core.security import decode_token

            payload = decode_token(authorization.removeprefix("Bearer "))
        except Exception:  # noqa: BLE001 - トークン不正時は未認証として扱えば十分
            return None
        if not payload or payload.get("type") != "access":
            return None
        subject = payload.get("sub")
        return str(subject) if subject else None

    async def _get_cached_response(self, key: str, request_hash: str) -> dict | None:
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.idempotency_key == key,
                        IdempotencyRecord.expires_at > datetime.now(UTC),
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
                expires_at = datetime.now(UTC) + timedelta(hours=IDEMPOTENCY_TTL_HOURS)

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
