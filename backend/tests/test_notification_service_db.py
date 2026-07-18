import pytest
from sqlalchemy import func, select

from app.models.models import WebhookDelivery
from app.schemas.schemas import NotificationCreate
from app.services import notification_service, webhook_service

pytestmark = pytest.mark.db


async def test_create_notification_persists(db_session, seed_company):
    tid, cid, uid = seed_company["tenant_id"], seed_company["company_id"], seed_company["user_id"]
    notif = await notification_service.create_notification(
        db_session, tid,
        NotificationCreate(company_id=cid, user_id=uid, category="approval", title="承認依頼", body="確認してください"),
    )
    assert notif.notification_id is not None

    items, total = await notification_service.list_notifications(db_session, tid, user_id=uid)
    assert total == 1
    assert items[0].title == "承認依頼"


async def test_webhook_channel_enqueues_delivery(db_session, seed_company):
    tid, cid, uid = seed_company["tenant_id"], seed_company["company_id"], seed_company["user_id"]
    # user opts into the webhook channel for this category
    await notification_service.upsert_preference(db_session, uid, "approval", channel_webhook=True)
    # a subscribed active endpoint exists
    await webhook_service.create_endpoint(
        db_session, tenant_id=tid, url="https://example.com/hook", secret="s3cr3t!!",
        subscribed_events=["notification.*"], company_id=cid,
    )

    await notification_service.create_notification(
        db_session, tid,
        NotificationCreate(company_id=cid, user_id=uid, category="approval", title="t", body="b"),
    )

    count = await db_session.scalar(select(func.count()).select_from(WebhookDelivery))
    assert count == 1
