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


async def test_delete_endpoint(db_session, seed_company):
    tid = seed_company["tenant_id"]
    ep = await webhook_service.create_endpoint(
        db_session, tenant_id=tid, url="https://example.com/h", secret="secret12", subscribed_events=["*"],
    )
    assert await webhook_service.delete_endpoint(db_session, ep.webhook_endpoint_id, tid) is True
    assert await webhook_service.list_endpoints(db_session, tid) == []
