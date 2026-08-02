"""GET /ops/health のDBクエリ回帰テスト。

statmerge時、ops.py は main の WebhookDelivery.company_id を前提にしていたが、
統合後の WebhookDelivery は company_id を持たず所属エンドポイント経由で会社に紐づく。
エンドポイント本体は認証チェーン(jose)importで環境依存的に落ちるため、ここでは
エンドポイントが用いるクエリ（WebhookDelivery→WebhookEndpoint join by company_id 等）を
直接実行し、会社スコープで正しく集計できることを検証する。
"""

import pytest
from sqlalchemy import select

from app.models.models import JobExecution, WebhookDelivery, WebhookEndpoint

pytestmark = pytest.mark.db


async def test_webhook_deliveries_are_scoped_by_company_via_endpoint(db_session, seed_company):
    cid = seed_company["company_id"]
    tid = seed_company["tenant_id"]

    endpoint = WebhookEndpoint(
        tenant_id=tid,
        company_id=cid,
        url="https://example.com/hook",
        secret="s3cr3t!!s3cr3t!!s3cr3t!!",
        subscribed_events=["*"],
        is_active=True,
    )
    db_session.add(endpoint)
    await db_session.flush()
    for st in ("delivered", "failed", "dead", "pending"):
        db_session.add(
            WebhookDelivery(
                webhook_endpoint_id=endpoint.webhook_endpoint_id,
                event_type="x.y",
                payload={},
                status=st,
                attempt_count=1,
            )
        )
    await db_session.flush()

    # ops.py が用いる join クエリを再現（company_idはエンドポイント経由）
    rows = await db_session.execute(
        select(WebhookDelivery.status)
        .join(
            WebhookEndpoint,
            WebhookDelivery.webhook_endpoint_id == WebhookEndpoint.webhook_endpoint_id,
        )
        .where(WebhookEndpoint.company_id == cid)
    )
    statuses = list(rows.scalars().all())
    assert len(statuses) == 4
    assert set(statuses) == {"delivered", "failed", "dead", "pending"}


async def test_job_executions_are_scoped_by_company(db_session, seed_company):
    cid = seed_company["company_id"]
    db_session.add(
        JobExecution(company_id=cid, job_type="monthly_close", status="succeeded", priority=100)
    )
    db_session.add(
        JobExecution(company_id=cid, job_type="monthly_close", status="dead", priority=100)
    )
    await db_session.flush()

    rows = await db_session.execute(
        select(JobExecution.status).where(JobExecution.company_id == cid)
    )
    statuses = list(rows.scalars().all())
    assert sorted(statuses) == ["dead", "succeeded"]
