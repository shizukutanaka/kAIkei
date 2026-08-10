"""Webhook配信サブシステム。

Webhook登録先(WebhookEndpoint)の管理と、イベント発生時の配信キュー
(WebhookDelivery)への投入・配信・指数バックオフ再試行を担う。

署名・バックオフ・イベント突合などのコアロジックは純粋関数として切り出し、
DB/ネットワークに依存せず単体テスト可能にしている。
"""
import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import random
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
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

ALLOWED_WEBHOOK_URL_SCHEMES = {"http", "https"}


class UnsafeWebhookUrlError(Exception):
    """Webhook URLがSSRF的に危険（内部/予約アドレス等）と判定された場合に送出する。"""


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


def is_unsafe_ip(ip_str: str) -> bool:
    """SSRF標的として危険なIPアドレス（プライベート/ループバック/リンクローカル等）か判定する。

    169.254.169.254（クラウドメタデータエンドポイント）は is_link_local に含まれる。
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # パースできないものは安全側に倒し危険扱いとする
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_webhook_url_scheme(url: str) -> str | None:
    """WebhookのURLがhttp/httpsスキーム・ホスト指定を持つか検証する（純粋・同期）。

    問題があれば理由文字列、なければNoneを返す。
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return "Invalid webhook URL"
    if parsed.scheme not in ALLOWED_WEBHOOK_URL_SCHEMES:
        return "Webhook URL must use http or https"
    if not parsed.hostname:
        return "Webhook URL must include a hostname"
    return None


async def _default_resolver(hostname: str, port: int):
    """既定の名前解決（実DNS）。テストではこの関数をmonkeypatchして差し替える。"""
    return await asyncio.get_event_loop().getaddrinfo(hostname, port)


async def resolve_and_check_safe(url: str, resolver=None) -> str | None:
    """WebhookのURLがSSRF的に安全かを検証する（名前解決込み）。

    登録時・配信直前の双方で呼び出す。配信直前にも呼ぶのは、登録後に
    DNSの応答が変化する（DNSリバインディング）ことで安全なホスト名が
    後から内部アドレスへ差し替わるケースへの対策。resolver省略時は
    _default_resolver（実DNS）を使う。テストではresolver引数を渡すか、
    モジュールの_default_resolverをmonkeypatchすることで実ネットワークに
    依存せず検証できる。

    Returns:
        問題があれば理由文字列、なければNone。
    """
    reason = validate_webhook_url_scheme(url)
    if reason:
        return reason
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolve = resolver or _default_resolver
    try:
        infos = await resolve(parsed.hostname, port)
    except OSError:
        return "Webhook URL hostname could not be resolved"
    for info in infos:
        addr = info[4][0]
        if is_unsafe_ip(addr):
            return f"Webhook URL resolves to a disallowed address ({addr})"
    return None


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
    """Webhook登録先を作成する。

    Raises:
        UnsafeWebhookUrlError: URLがSSRF的に危険（内部/予約アドレス等）な場合。
    """
    unsafe_reason = await resolve_and_check_safe(url)
    if unsafe_reason:
        raise UnsafeWebhookUrlError(unsafe_reason)
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
    now = datetime.now(UTC)
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
    now = datetime.now(UTC)
    timestamp = int(now.timestamp())
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: sign_payload(endpoint.secret, body, timestamp),
        TIMESTAMP_HEADER: str(timestamp),
        EVENT_HEADER: delivery.event_type,
    }
    delivery.attempt_count += 1

    # 配信直前にもURL安全性を再検証する（DNSリバインディング対策。登録時チェックだけでは
    # 登録後にホスト名の解決結果が内部アドレスへ変化するケースを防げない）。
    unsafe_reason = await resolve_and_check_safe(endpoint.url)
    if unsafe_reason:
        delivery.last_status_code = None
        delivery.last_error = f"Blocked: {unsafe_reason}"
        logger.warning(
            "Webhook delivery %s blocked (unsafe URL): %s", delivery.webhook_delivery_id, unsafe_reason
        )
    else:
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


async def process_due_deliveries(
    db: AsyncSession, limit: int = 50, tenant_id: UUID | None = None
) -> int:
    """再試行時刻を過ぎたpending配信を処理する。

    tenant_id指定時はそのテナントのエンドポイント宛ての配信のみを対象とする
    （テナント管理者が手動トリガーするAPI用。バックグラウンドワーカーは
    tenant_id未指定で全テナントを対象に呼び出す）。

    各配信は SELECT ... FOR UPDATE SKIP LOCKED で個別に確保してから送信する。
    これにより、同時に複数のワーカー/手動トリガーが実行されても同一配信が
    二重送信されない（確保できなかった配信は他の実行者が処理中とみなしスキップする）。

    Returns:
        送信を試行した件数。
    """
    now = datetime.now(UTC)
    id_query = (
        select(WebhookDelivery.webhook_delivery_id)
        .join(
            WebhookEndpoint,
            WebhookDelivery.webhook_endpoint_id == WebhookEndpoint.webhook_endpoint_id,
        )
        .where(
            WebhookDelivery.status == "pending",
            WebhookDelivery.next_retry_at <= now,
            WebhookEndpoint.is_active == True,  # noqa: E712
        )
    )
    if tenant_id is not None:
        id_query = id_query.where(WebhookEndpoint.tenant_id == tenant_id)
    id_query = id_query.order_by(WebhookDelivery.next_retry_at).limit(limit)

    due_ids = [row[0] for row in (await db.execute(id_query)).all()]

    processed = 0
    for delivery_id in due_ids:
        locked_result = await db.execute(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.webhook_delivery_id == delivery_id,
                WebhookDelivery.status == "pending",
            )
            .with_for_update(skip_locked=True)
        )
        delivery = locked_result.scalar_one_or_none()
        if delivery is None:
            continue  # 他の実行者が既に確保済み、または状態が変化した

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
    if delivery is None or delivery.status == "delivered":
        # 配信済み(delivered)は再キュー対象外（顧客側への重複配信を防ぐ）。
        return None
    delivery.status = "pending"
    delivery.attempt_count = 0
    delivery.next_retry_at = datetime.now(UTC)
    delivery.last_error = None
    delivery.last_status_code = None
    await db.commit()
    await db.refresh(delivery)
    return delivery
