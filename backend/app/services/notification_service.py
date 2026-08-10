import logging
from datetime import UTC
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Notification, NotificationPreference
from app.schemas.schemas import NotificationCreate

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {
    "approval", "journal", "payroll", "expense", "invoice",
    "tax", "audit", "system", "ai", "period_close",
}

VALID_PRIORITIES = {"low", "normal", "high", "urgent"}

# 配信チャネル（アプリ内 + 外部）。外部チャネルの実配信はフェーズ7の配信基盤で行う。
DELIVERY_CHANNELS = ("inapp", "email", "push", "webhook")


def resolve_delivery_channels(pref: NotificationPreference | None) -> list[str]:
    """通知設定から有効な配信チャネルの一覧を解決する。

    設定行が存在しない場合は、NotificationPreferenceのカラム既定値
    （channel_inappのみTrue）に合わせてアプリ内通知のみを返す。

    Args:
        pref: 対象ユーザー・カテゴリの通知設定。未設定の場合はNone。

    Returns:
        有効な配信チャネル名のリスト（DELIVERY_CHANNELSの順序を保持）。
    """
    if pref is None:
        return ["inapp"]
    flags = {
        "inapp": pref.channel_inapp,
        "email": pref.channel_email,
        "push": pref.channel_push,
        "webhook": pref.channel_webhook,
    }
    return [channel for channel in DELIVERY_CHANNELS if flags[channel]]


async def create_notification(
    db: AsyncSession,
    tenant_id: UUID,
    payload: NotificationCreate,
) -> Notification:
    """通知を作成する。

    アプリ内通知レコード（システム記録）を永続化したうえで、受信者の通知設定を
    参照して有効な外部配信チャネル（メール/プッシュ/Webhook）を解決する。
    外部配信の実処理はフェーズ7の配信基盤で行うため、ここでは配信意図を記録する。
    """
    if payload.category not in VALID_CATEGORIES:
        raise ValueError(f"Invalid category: {payload.category}")
    if payload.priority not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority: {payload.priority}")

    notif = Notification(
        tenant_id=tenant_id,
        company_id=payload.company_id,
        user_id=payload.user_id,
        category=payload.category,
        priority=payload.priority,
        title=payload.title,
        body=payload.body,
        action_url=payload.action_url,
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)

    # 受信者の通知設定に応じて外部配信チャネルを解決する。
    if payload.user_id is not None:
        pref_result = await db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == payload.user_id,
                NotificationPreference.category == payload.category,
            )
        )
        channels = resolve_delivery_channels(pref_result.scalar_one_or_none())
        external = [c for c in channels if c != "inapp"]
        if external:
            logger.info(
                "Notification %s queued for external delivery channels: %s",
                notif.notification_id,
                ", ".join(external),
            )
        # Webhookチャネルが有効なら、購読中エンドポイントへ配信キューへ投入する。
        # 配信の失敗が通知作成自体を妨げないよう防御的に扱う。
        if "webhook" in external:
            try:
                from app.services import webhook_service

                await webhook_service.enqueue_event(
                    db,
                    tenant_id=tenant_id,
                    event_type=f"notification.{payload.category}",
                    data={
                        "notification_id": str(notif.notification_id),
                        "category": notif.category,
                        "priority": notif.priority,
                        "title": notif.title,
                        "body": notif.body,
                        "action_url": notif.action_url,
                        "company_id": str(notif.company_id) if notif.company_id else None,
                    },
                    company_id=payload.company_id,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Failed to enqueue webhook delivery for notification %s: %s",
                    notif.notification_id,
                    e,
                )

    return notif


async def list_notifications(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID | None = None,
    company_id: UUID | None = None,
    unread_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Notification], int]:
    """通知一覧を取得する。"""
    conditions = [Notification.tenant_id == tenant_id]
    if user_id:
        conditions.append(Notification.user_id == user_id)
    if company_id:
        conditions.append(Notification.company_id == company_id)
    if unread_only:
        conditions.append(Notification.is_read == False)  # noqa: E712

    count_result = await db.execute(
        select(func.count()).select_from(Notification).where(*conditions)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Notification)
        .where(*conditions)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(result.scalars().all())
    return items, total


async def mark_as_read(
    db: AsyncSession,
    notification_id: UUID,
    tenant_id: UUID,
) -> Notification | None:
    """通知を既読にする。"""
    result = await db.execute(
        select(Notification).where(
            Notification.notification_id == notification_id,
            Notification.tenant_id == tenant_id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        return None
    if not notif.is_read:
        notif.is_read = True
        from datetime import datetime
        notif.read_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(notif)
    return notif


async def mark_all_as_read(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
) -> int:
    """ユーザーの全通知を既読にする。"""
    from datetime import datetime
    now = datetime.now(UTC)
    result = await db.execute(
        update(Notification)
        .where(
            Notification.tenant_id == tenant_id,
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True, read_at=now)
    )
    await db.commit()
    return result.rowcount


async def get_unread_count(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
) -> int:
    """未読通知数を取得する。"""
    result = await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    return result.scalar() or 0


async def get_preferences(
    db: AsyncSession,
    user_id: UUID,
) -> list[NotificationPreference]:
    """ユーザーの通知設定を取得する。"""
    result = await db.execute(
        select(NotificationPreference)
        .where(NotificationPreference.user_id == user_id)
        .order_by(NotificationPreference.category)
    )
    return list(result.scalars().all())


async def upsert_preference(
    db: AsyncSession,
    user_id: UUID,
    category: str,
    channel_inapp: bool | None = None,
    channel_email: bool | None = None,
    channel_push: bool | None = None,
    channel_webhook: bool | None = None,
) -> NotificationPreference:
    """通知設定を作成または更新する。"""
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.category == category,
        )
    )
    pref = result.scalar_one_or_none()

    if pref:
        if channel_inapp is not None:
            pref.channel_inapp = channel_inapp
        if channel_email is not None:
            pref.channel_email = channel_email
        if channel_push is not None:
            pref.channel_push = channel_push
        if channel_webhook is not None:
            pref.channel_webhook = channel_webhook
    else:
        pref = NotificationPreference(
            user_id=user_id,
            category=category,
            channel_inapp=channel_inapp if channel_inapp is not None else True,
            channel_email=channel_email if channel_email is not None else False,
            channel_push=channel_push if channel_push is not None else False,
            channel_webhook=channel_webhook if channel_webhook is not None else False,
        )
        db.add(pref)

    await db.commit()
    await db.refresh(pref)
    return pref
