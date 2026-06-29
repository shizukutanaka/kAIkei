from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.schemas.schemas import (
    NotificationResponse,
    NotificationListResponse,
    NotificationCreate,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
)
from app.services.notification_service import (
    create_notification,
    list_notifications,
    mark_as_read,
    mark_all_as_read,
    get_unread_count,
    get_preferences,
    upsert_preference,
    VALID_CATEGORIES,
)

router = APIRouter()


@router.get("", response_model=NotificationListResponse)
async def list_user_notifications(
    company_id: UUID | None = Query(None),
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    """通知一覧を取得する。"""
    items, total = await list_notifications(
        db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        company_id=company_id,
        unread_only=unread_only,
        page=page,
        page_size=page_size,
    )
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count")
async def unread_count(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """未読通知数を取得する。"""
    count = await get_unread_count(db, current_user.tenant_id, current_user.user_id)
    return {"unread_count": count}


@router.post("/mark-read/{notification_id}", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    """通知を既読にする。"""
    notif = await mark_as_read(db, notification_id, current_user.tenant_id)
    if not notif:
        raise HTTPException(status_code=404, detail="通知が見つかりません")
    return NotificationResponse.model_validate(notif)


@router.post("/mark-all-read")
async def mark_all_notifications_read(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """全通知を既読にする。"""
    count = await mark_all_as_read(db, current_user.tenant_id, current_user.user_id)
    return {"marked_count": count}


@router.post("", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
async def create_notification_endpoint(
    payload: NotificationCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    """通知を作成する（システム内部用）。"""
    try:
        notif = await create_notification(db, current_user.tenant_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return NotificationResponse.model_validate(notif)


@router.get("/preferences", response_model=list[NotificationPreferenceResponse])
async def list_preferences(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationPreferenceResponse]:
    """通知設定一覧を取得する。"""
    prefs = await get_preferences(db, current_user.user_id)
    return [NotificationPreferenceResponse.model_validate(p) for p in prefs]


@router.put("/preferences/{category}", response_model=NotificationPreferenceResponse)
async def update_preference(
    category: str,
    payload: NotificationPreferenceUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationPreferenceResponse:
    """通知設定を更新する。"""
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"無効なカテゴリ: {category}")
    pref = await upsert_preference(
        db,
        current_user.user_id,
        category,
        channel_inapp=payload.channel_inapp,
        channel_email=payload.channel_email,
        channel_push=payload.channel_push,
        channel_webhook=payload.channel_webhook,
    )
    return NotificationPreferenceResponse.model_validate(pref)
