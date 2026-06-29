import logging
from uuid import UUID

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Notification, NotificationPreference, User
from app.schemas.schemas import NotificationCreate

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {
    "approval", "journal", "payroll", "expense", "invoice",
    "tax", "audit", "system", "ai", "period_close",
}

VALID_PRIORITIES = {"low", "normal", "high", "urgent"}


async def create_notification(
    db: AsyncSession,
    tenant_id: UUID,
    payload: NotificationCreate,
) -> Notification:
    """通知を作成する。"""
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
        from datetime import datetime, timezone
        notif.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notif)
    return notif


async def mark_all_as_read(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
) -> int:
    """ユーザーの全通知を既読にする。"""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
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
