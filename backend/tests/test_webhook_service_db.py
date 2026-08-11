import pytest

from app.services import webhook_service

pytestmark = pytest.mark.db


class _FakeResponse:
    status_code = 200


class _FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return _FakeResponse()


@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch):
    """DBテストは実DNSに依存させない（ネットワークなしで決定的に実行するため）。

    SSRF検証ロジック自体はtest_webhooks.pyでフェイクresolverを注入して検証済み。
    """
    async def _always_public(hostname, port):
        return [(2, 1, 6, "", ("8.8.8.8", port))]

    monkeypatch.setattr(webhook_service, "_default_resolver", _always_public)


async def test_enqueue_and_deliver(db_session, seed_company, monkeypatch):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    endpoint = await webhook_service.create_endpoint(
        db_session, tenant_id=tid, url="https://example.com/hook", secret="s3cr3t!!",
        subscribed_events=["notification.*"], company_id=cid,
    )

    # matching event -> a pending delivery is enqueued
    created = await webhook_service.enqueue_event(
        db_session, tenant_id=tid, event_type="notification.approval", data={"x": 1}, company_id=cid,
    )
    assert len(created) == 1
    assert created[0].status == "pending"

    # non-matching event -> nothing enqueued
    none = await webhook_service.enqueue_event(db_session, tenant_id=tid, event_type="journal.posted", data={})
    assert none == []

    # deliver with a stubbed HTTP client -> delivered
    monkeypatch.setattr(webhook_service.httpx, "AsyncClient", _FakeClient)
    ok = await webhook_service.attempt_delivery(db_session, created[0], endpoint)
    assert ok is True
    assert created[0].status == "delivered"
    assert created[0].last_status_code == 200


async def test_create_endpoint_rejects_unsafe_url(db_session, seed_company, monkeypatch):
    async def _resolves_private(hostname, port):
        return [(2, 1, 6, "", ("10.0.0.5", port))]

    monkeypatch.setattr(webhook_service, "_default_resolver", _resolves_private)
    tid = seed_company["tenant_id"]
    with pytest.raises(webhook_service.UnsafeWebhookUrlError):
        await webhook_service.create_endpoint(
            db_session, tenant_id=tid, url="http://internal.example/hook",
            secret="s3cr3t!!s3cr3t!!s3cr3t!!", subscribed_events=["*"],
        )


async def test_attempt_delivery_blocks_url_that_resolves_unsafe_at_send_time(
    db_session, seed_company, monkeypatch
):
    """登録時は安全でも、配信直前の再検証で内部アドレスに解決されれば送信をブロックする。"""
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    endpoint = await webhook_service.create_endpoint(
        db_session, tenant_id=tid, url="https://example.com/hook", secret="s3cr3t!!s3cr3t!!s3cr3t!!",
        subscribed_events=["*"], company_id=cid,
    )
    created = await webhook_service.enqueue_event(db_session, tenant_id=tid, event_type="x.y", data={})

    async def _resolves_private(hostname, port):
        return [(2, 1, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(webhook_service, "_default_resolver", _resolves_private)
    called = False

    class _TrackingClient(_FakeClient):
        async def post(self, *args, **kwargs):
            nonlocal called
            called = True
            return _FakeResponse()

    monkeypatch.setattr(webhook_service.httpx, "AsyncClient", _TrackingClient)

    ok = await webhook_service.attempt_delivery(db_session, created[0], endpoint)
    assert ok is False
    assert called is False  # HTTPクライアントは一切呼ばれない
    assert "Blocked" in created[0].last_error


async def test_delete_endpoint(db_session, seed_company):
    tid = seed_company["tenant_id"]
    ep = await webhook_service.create_endpoint(
        db_session, tenant_id=tid, url="https://example.com/h", secret="secret12secret12secret12",
        subscribed_events=["*"],
    )
    assert await webhook_service.delete_endpoint(db_session, ep.webhook_endpoint_id, tid) is True
    assert await webhook_service.list_endpoints(db_session, tid) == []


async def test_replay_resets_failed_delivery(db_session, seed_company):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    await webhook_service.create_endpoint(
        db_session, tenant_id=tid, url="https://example.com/hook", secret="s3cr3t!!s3cr3t!!s3cr3t!!",
        subscribed_events=["*"], company_id=cid,
    )
    created = await webhook_service.enqueue_event(db_session, tenant_id=tid, event_type="x.y", data={})
    delivery = created[0]
    # 失敗状態（DLQ相当）を模擬
    delivery.status = "failed"
    delivery.attempt_count = 5
    delivery.last_error = "boom"
    delivery.last_status_code = 500
    await db_session.commit()

    replayed = await webhook_service.replay_delivery(db_session, delivery.webhook_delivery_id, tid)
    assert replayed is not None
    assert replayed.status == "pending"
    assert replayed.attempt_count == 0
    assert replayed.last_error is None

    # 他テナントからは不可
    from uuid import uuid4
    assert await webhook_service.replay_delivery(db_session, delivery.webhook_delivery_id, uuid4()) is None


async def test_replay_rejects_already_delivered(db_session, seed_company):
    """配信済み(delivered)の配信は再キューできない（顧客側への重複配信防止）。"""
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    await webhook_service.create_endpoint(
        db_session, tenant_id=tid, url="https://example.com/hook", secret="s3cr3t!!s3cr3t!!s3cr3t!!",
        subscribed_events=["*"], company_id=cid,
    )
    created = await webhook_service.enqueue_event(db_session, tenant_id=tid, event_type="x.y", data={})
    delivery = created[0]
    delivery.status = "delivered"
    await db_session.commit()

    assert await webhook_service.replay_delivery(db_session, delivery.webhook_delivery_id, tid) is None


async def test_process_due_deliveries_scopes_to_tenant(db_session, seed_company, monkeypatch):
    """tenant_id指定時は、他テナント宛ての配信を処理しない。"""

    from app.models.models import Company, Tenant

    tid, cid = seed_company["tenant_id"], seed_company["company_id"]

    other_tenant = Tenant(tenant_name="Other Tenant", tenant_code="OTHER-WH")
    db_session.add(other_tenant)
    await db_session.flush()
    other_company = Company(tenant_id=other_tenant.tenant_id, company_name="Other Co", company_code="OC1")
    db_session.add(other_company)
    await db_session.flush()

    await webhook_service.create_endpoint(
        db_session, tenant_id=tid, url="https://example.com/mine", secret="s3cr3t!!s3cr3t!!s3cr3t!!",
        subscribed_events=["*"], company_id=cid,
    )
    await webhook_service.create_endpoint(
        db_session, tenant_id=other_tenant.tenant_id, url="https://example.com/other",
        secret="s3cr3t!!s3cr3t!!s3cr3t!!", subscribed_events=["*"], company_id=other_company.company_id,
    )

    await webhook_service.enqueue_event(db_session, tenant_id=tid, event_type="x.y", data={})
    await webhook_service.enqueue_event(db_session, tenant_id=other_tenant.tenant_id, event_type="x.y", data={})

    monkeypatch.setattr(webhook_service.httpx, "AsyncClient", _FakeClient)

    processed = await webhook_service.process_due_deliveries(db_session, tenant_id=tid)
    assert processed == 1

    mine = await webhook_service.list_deliveries(
        db_session, (await webhook_service.list_endpoints(db_session, tid))[0].webhook_endpoint_id
    )
    others = await webhook_service.list_deliveries(
        db_session,
        (await webhook_service.list_endpoints(db_session, other_tenant.tenant_id))[0].webhook_endpoint_id,
    )
    assert mine[0].status == "delivered"
    assert others[0].status == "pending"  # 他テナントの配信は手を付けられていない


async def test_process_due_deliveries_skips_inactive_endpoint(db_session, seed_company, monkeypatch):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    endpoint = await webhook_service.create_endpoint(
        db_session, tenant_id=tid, url="https://example.com/hook", secret="s3cr3t!!s3cr3t!!s3cr3t!!",
        subscribed_events=["*"], company_id=cid,
    )
    created = await webhook_service.enqueue_event(db_session, tenant_id=tid, event_type="x.y", data={})
    endpoint.is_active = False
    await db_session.commit()

    monkeypatch.setattr(webhook_service.httpx, "AsyncClient", _FakeClient)
    processed = await webhook_service.process_due_deliveries(db_session)
    assert processed == 0
    await db_session.refresh(created[0])
    assert created[0].status == "pending"
