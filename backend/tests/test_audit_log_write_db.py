"""監査ログが実際に書き込まれることの検証。

ミドルウェアは `tenant_id` に固定のゼロUUIDを入れていたため、tenants への
外部キー制約に必ず違反し、**監査ログが1件も残らない**状態だった。例外は
握り潰されて警告ログになるだけなので、動作しているように見えていた。

会計システムの操作証跡は電子帳簿保存法の要請でもあり、「書けているつもりで
1件も無い」は最悪の壊れ方なので、実際に行が増えることを確認する。
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.middleware.audit_log import _tenant_of
from app.models.models import AuditLog, Company, Tenant, User

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def seeded(db_session):
    tenant = Tenant(tenant_name="監査テナント", tenant_code=f"AU-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()

    company = Company(
        tenant_id=tenant.tenant_id,
        company_name="監査会社",
        company_code=f"AU-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(company)
    await db_session.flush()

    user = User(
        tenant_id=tenant.tenant_id,
        email=f"audit-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="監査ユーザー",
        role="accountant",
    )
    db_session.add(user)
    await db_session.flush()
    return {"tenant_id": tenant.tenant_id, "user_id": user.user_id}


async def _count(db_session) -> int:
    return (await db_session.execute(select(func.count()).select_from(AuditLog))).scalar_one()


async def test_tenant_is_resolved_from_the_user(db_session, seeded):
    assert await _tenant_of(db_session, seeded["user_id"]) == seeded["tenant_id"]


async def test_unknown_user_resolves_to_none(db_session, seeded):
    """存在しないユーザーIDでも例外にせず None を返す（認証前イベント用）。"""
    assert await _tenant_of(db_session, uuid.uuid4()) is None
    assert await _tenant_of(db_session, None) is None


async def test_log_with_resolved_tenant_is_persisted(db_session, seeded):
    """テナントを引けた場合、行が実際に増えること。"""
    before = await _count(db_session)
    db_session.add(
        AuditLog(
            tenant_id=seeded["tenant_id"],
            user_id=seeded["user_id"],
            action="post",
            resource_type="journals",
            method="POST",
            path="/api/v1/journals",
            status_code=201,
        )
    )
    await db_session.flush()

    assert await _count(db_session) == before + 1


async def test_log_without_tenant_is_persisted(db_session):
    """認証前イベント（テナント不明）も捨てずに残せること。

    tenant_id が NOT NULL のままだとここで外部キー／NOT NULL 違反になる。
    """
    before = await _count(db_session)
    db_session.add(
        AuditLog(
            tenant_id=None,
            user_id=None,
            action="post",
            resource_type="auth",
            method="POST",
            path="/api/v1/auth/login",
            status_code=401,
        )
    )
    await db_session.flush()

    assert await _count(db_session) == before + 1


async def test_zero_uuid_tenant_is_rejected(db_session):
    """旧実装が入れていた固定のゼロUUIDは、外部キー違反で書き込めないこと。

    「固定値でも通っていたのでは」という誤解を残さないため、明示的に確認する。
    """
    from sqlalchemy.exc import IntegrityError

    db_session.add(
        AuditLog(
            tenant_id=uuid.UUID(int=0),
            user_id=None,
            action="post",
            resource_type="journals",
            method="POST",
            path="/api/v1/journals",
            status_code=201,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()
