"""Pytest fixtures for DB integration tests.

DB-marked tests require a real PostgreSQL (models use JSONB/UUID). Configure the
test database via TEST_DATABASE_URL, e.g.:
    TEST_DATABASE_URL=postgresql+asyncpg://kaikei:kaikei_dev@localhost:5432/kaikei_test

When TEST_DATABASE_URL is unset, all @pytest.mark.db tests are skipped so the
pure-logic suite still runs with no database.
"""
import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def pytest_collection_modifyitems(config, items):
    """Skip DB-marked tests when no test database is configured."""
    if TEST_DATABASE_URL:
        return
    skip_db = pytest.mark.skip(reason="TEST_DATABASE_URL not set; skipping DB integration tests")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Create the full schema once per session, drop it at the end."""
    if not TEST_DATABASE_URL:
        yield
        return

    import app.models.models  # noqa: F401  -- registers all tables on Base.metadata
    from app.core.database import Base

    async def _init():
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    async def _teardown():
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(_init())
    yield
    asyncio.run(_teardown())


@pytest_asyncio.fixture
async def db_session():
    """A per-test AsyncSession wrapped in an outer transaction that is rolled
    back after each test. join_transaction_mode='create_savepoint' lets the
    code-under-test call commit() without escaping the test's isolation."""
    engine = create_async_engine(TEST_DATABASE_URL)
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def seed_company(db_session):
    """Insert a Tenant + Company + User and return their ids for FK use."""
    from app.models.models import Company, Tenant, User

    tenant = Tenant(tenant_name="Test Tenant", tenant_code="TEST")
    db_session.add(tenant)
    await db_session.flush()

    company = Company(tenant_id=tenant.tenant_id, company_name="Test Co", company_code="TC1")
    db_session.add(company)
    await db_session.flush()

    user = User(
        tenant_id=tenant.tenant_id,
        email="tester@example.com",
        password_hash="x",
        display_name="Tester",
        role="accountant",
    )
    db_session.add(user)
    await db_session.flush()

    return {
        "tenant_id": tenant.tenant_id,
        "company_id": company.company_id,
        "user_id": user.user_id,
    }
