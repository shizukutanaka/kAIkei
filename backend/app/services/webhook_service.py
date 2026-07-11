"""Webhook配信サブシステム。

Webhook登録先(WebhookEndpoint)の管理と、イベント発生時の配信キュー
(WebhookDelivery)への投入・配信・指数バックオフ再試行を担う。

署名・バックオフ・イベント突合などのコアロジックは純粋関数として切り出し、
DB/ネットワークに依存せず単体テスト可能にしている。
"""
import hashlib
import hmac
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger(__name__)

# 指数バックオフの基準秒数と上限。
BACKOFF_BASE_SECONDS = 60
BACKOFF_MAX_SECONDS = 3600
DELIVERY_TIMEOUT_SECONDS = 10.0

SIGNATURE_HEADER = "X-Kaikei-Signature"
TIMESTAMP_HEADER = "X-Kaikei-Timestamp"
EVENT_HEADER = "X-Kaikei-Event"

# リプレイ防止: 署名タイムスタンプの許容ウィンドウ（秒）。
SIGNATURE_TOLERANCE_SECONDS = 300


# --- 純粋関数（DB非依存・テスト可能） ---------------------------------------

def serialize_payload(payload: dict) -> bytes:
    """ペイロードを署名・送信用に決定的なJSONバイト列へ直列化する。"""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sign_payload(secret: str, body: bytes, timestamp: int | None = None) -> str:
    """HMAC-SHA256でペイロードに署名する。返り値は "sha256=<hex>"。

    timestamp指定時は "{timestamp}.{body}" を署名対象にし、署名の再利用
    （リプレイ攻撃）を防ぐ。Stripe/GitHub等と同方式。
    """
    message = body if timestamp is None else f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(
    secret: str,
    body: bytes,
    signature: str,
    timestamp: int | None = None,
    now: int | None = None,
    tolerance_seconds: int = SIGNATURE_TOLERANCE_SECONDS,
) -> bool:
    """署名を定数時間比較で検証する。

    timestamp/now指定時は許容ウィンドウ外（期限切れ・未来時刻）を拒否したうえで、
    タイムスタンプ込みの署名を検証する。
    """
    if timestamp is not None and now is not None:
        if timestamp > now + tolerance_seconds:
            return False
        if now - timestamp > tolerance_seconds:
            return False
    expected = sign_payload(secret, body, timestamp)
    return hmac.compare_digest(expected, signature or "")


def compute_backoff_seconds(attempt: int) -> int:
    """失敗した試行回数(1始まり)に対する次回再試行までの秒数を計算する。

    指数バックオフ: BASE * 2**(attempt-1) を上限BACKOFF_MAX_SECONDSでクリップ。
    """
    if attempt < 1:
        attempt = 1
    return min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), BACKOFF_MAX_SECONDS)


def event_matches(subscribed_events: list[str], event_type: str) -> bool:
    """購読イベント指定がイベント種別に一致するか判定する。

    - "*"            … 全イベントに一致
    - "notification.*" … 接頭辞一致（"notification." で始まるもの）
    - それ以外       … 完全一致
    """
    for pattern in subscribed_events or []:
        if pattern == "*" or pattern == event_type:
            return True
        if pattern.endswith(".*") and event_type.startswith(pattern[:-1]):
            return True
    return False


def build_event_payload(event_type: str, data: dict, event_id: str, occurred_at: str) -> dict:
    """配信するイベントペイロードを組み立てる。"""
    return {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "data": data,
    }


# --- 非同期サービス（DB/ネットワーク依存） ----------------------------------

async def create_endpoint(
    db: AsyncSession,
    tenant_id: UUID,
    url: str,
    secret: str,
    subscribed_events: list[str],
    company_id: UUID | None = None,
    description: str | None = None,
) -> WebhookEndpoint:
    """Webhook登録先を作成する。"""
    endpoint = WebhookEndpoint(
        tenant_id=tenant_id,
        company_id=company_id,
        url=url,
        secret=secret,
        subscribed_events=subscribed_events or [],
        description=description,
        is_active=True,
    )
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    return endpoint


async def list_endpoints(
    db: AsyncSession,
    tenant_id: UUID,
    company_id: UUID | None = None,
    active_only: bool = False,
) -> list[WebhookEndpoint]:
    """テナントのWebhook登録先を一覧取得する。"""
    conditions = [WebhookEndpoint.tenant_id == tenant_id]
    if company_id is not None:
        conditions.append(WebhookEndpoint.company_id == company_id)
    if active_only:
        conditions.append(WebhookEndpoint.is_active == True)  # noqa: E712
    result = await db.execute(
        select(WebhookEndpoint).where(*conditions).order_by(WebhookEndpoint.created_at.desc())
    )
    return list(result.scalars().all())


async def get_endpoint(
    db: AsyncSession, endpoint_id: UUID, tenant_id: UUID
) -> WebhookEndpoint | None:
    """Webhook登録先を1件取得する（テナント境界を強制）。"""
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.webhook_endpoint_id == endpoint_id,
            WebhookEndpoint.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_endpoint(db: AsyncSession, endpoint_id: UUID, tenant_id: UUID) -> bool:
    """Webhook登録先を削除する。存在すればTrue。"""
    endpoint = await get_endpoint(db, endpoint_id, tenant_id)
    if endpoint is None:
        return False
    await db.delete(endpoint)
    await db.commit()
    return True


async def list_deliveries(
    db: AsyncSession,
    endpoint_id: UUID,
    status: str | None = None,
    limit: int = 50,
) -> list[WebhookDelivery]:
    """指定エンドポイントの配信履歴を取得する。"""
    conditions = [WebhookDelivery.webhook_endpoint_id == endpoint_id]
    if status is not None:
        conditions.append(WebhookDelivery.status == status)
    result = await db.execute(
        select(WebhookDelivery)
        .where(*conditions)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def enqueue_event(
    db: AsyncSession,
    tenant_id: UUID,
    event_type: str,
    data: dict,
    company_id: UUID | None = None,
) -> list[WebhookDelivery]:
    """イベントを購読中のアクティブなエンドポイントへ配信キューへ投入する。

    一致するエンドポイントごとにpending状態のWebhookDeliveryを作成して返す。
    実際の送信はattempt_delivery/process_due_deliveriesが行う。
    """
    endpoints = await list_endpoints(db, tenant_id, active_only=True)
    now = datetime.now(timezone.utc)
    event_id = str(uuid4())
    payload = build_event_payload(event_type, data, event_id, now.isoformat())

    created: list[WebhookDelivery] = []
    for endpoint in endpoints:
        if company_id is not None and endpoint.company_id not in (None, company_id):
            continue
        if not event_matches(endpoint.subscribed_events, event_type):
            continue
        delivery = WebhookDelivery(
            webhook_endpoint_id=endpoint.webhook_endpoint_id,
            event_type=event_type,
            payload=payload,
            status="pending",
            attempt_count=0,
            next_retry_at=now,
        )
        db.add(delivery)
        created.append(delivery)

    if created:
        await db.commit()
        for delivery in created:
            await db.refresh(delivery)
    return created


async def attempt_delivery(
    db: AsyncSession, delivery: WebhookDelivery, endpoint: WebhookEndpoint
) -> bool:
    """1件の配信を試行し、結果に応じて状態・再試行時刻を更新する。

    2xx応答で "delivered"、それ以外は試行回数を加算し、上限未満なら
    指数バックオフでnext_retry_atを設定、上限到達で "failed" とする。
    """
    body = serialize_payload(delivery.payload)
    now = datetime.now(timezone.utc)
    timestamp = int(now.timestamp())
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: sign_payload(endpoint.secret, body, timestamp),
        TIMESTAMP_HEADER: str(timestamp),
        EVENT_HEADER: delivery.event_type,
    }
    delivery.attempt_count += 1

    try:
        async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as client:
            response = await client.post(endpoint.url, content=body, headers=headers)
        delivery.last_status_code = response.status_code
        if 200 <= response.status_code < 300:
            delivery.status = "delivered"
            delivery.delivered_at = now
            delivery.next_retry_at = None
            delivery.last_error = None
            await db.commit()
            await db.refresh(delivery)
            return True
        delivery.last_error = f"HTTP {response.status_code}"
    except Exception as e:  # noqa: BLE001 - 送信失敗は種別を問わず再試行対象
        delivery.last_status_code = None
        delivery.last_error = str(e)[:500]
        logger.warning("Webhook delivery %s failed: %s", delivery.webhook_delivery_id, e)

    if delivery.attempt_count >= delivery.max_attempts:
        delivery.status = "failed"
        delivery.next_retry_at = None
    else:
        delivery.status = "pending"
        backoff = compute_backoff_seconds(delivery.attempt_count)
        # 同時多発失敗時の再試行集中（thundering herd）を避けるため±20%のジッターを付与。
        jitter = random.uniform(0.8, 1.2)
        delivery.next_retry_at = now + timedelta(seconds=int(backoff * jitter))
    await db.commit()
    await db.refresh(delivery)
    return False


async def process_due_deliveries(db: AsyncSession, limit: int = 50) -> int:
    """再試行時刻を過ぎたpending配信を処理する（配信ワーカー用）。

    Returns:
        送信を試行した件数。
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.status == "pending",
            WebhookDelivery.next_retry_at <= now,
        )
        .order_by(WebhookDelivery.next_retry_at)
        .limit(limit)
    )
    due = list(result.scalars().all())

    processed = 0
    for delivery in due:
        endpoint_result = await db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.webhook_endpoint_id == delivery.webhook_endpoint_id
            )
        )
        endpoint = endpoint_result.scalar_one_or_none()
        if endpoint is None or not endpoint.is_active:
            continue
        await attempt_delivery(db, delivery, endpoint)
        processed += 1
    return processed


async def replay_delivery(
    db: AsyncSession, delivery_id: UUID, tenant_id: UUID
) -> WebhookDelivery | None:
    """失敗（DLQ相当）または保留中の配信を再キューする。

    次回のprocess_due_deliveriesで再送されるよう、状態をpendingへ戻し試行回数と
    エラーをリセットする。テナント境界はエンドポイント経由で強制する。
    """
    result = await db.execute(
        select(WebhookDelivery)
        .join(
            WebhookEndpoint,
            WebhookDelivery.webhook_endpoint_id == WebhookEndpoint.webhook_endpoint_id,
        )
        .where(
            WebhookDelivery.webhook_delivery_id == delivery_id,
            WebhookEndpoint.tenant_id == tenant_id,
        )
    )
    delivery = result.scalar_one_or_none()
    if delivery is None:
        return None
    delivery.status = "pending"
    delivery.attempt_count = 0
    delivery.next_retry_at = datetime.now(timezone.utc)
    delivery.last_error = None
    delivery.last_status_code = None
    await db.commit()
    await db.refresh(delivery)
    return delivery
