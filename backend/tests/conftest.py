"""Pytest fixtures for DB integration tests.

DB-marked tests require a real PostgreSQL (models use JSONB/UUID). Configure the
test database via TEST_DATABASE_URL, e.g.:
    TEST_DATABASE_URL=postgresql+asyncpg://kaikei:kaikei_dev@localhost:5432/kaikei_test

When TEST_DATABASE_URL is unset, all @pytest.mark.db tests are skipped so the
pure-logic suite still runs with no database.
"""
import asyncio
import os
import pathlib

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

TESTS_DIR = str(pathlib.Path(__file__).parent)


def _provision_ci_database() -> None:
    """CI で TEST_DATABASE_URL が無ければ、自前で PostgreSQL を用意する。

    DBを要するテストは金額と権限に直結する（テナント分離・給与・消費税）が、
    CI では一度も実行されていなかった。ワークフローに Postgres サービスを
    足すのが本来だが `workflows` 権限が無いため、ランナーに導入済みの
    PostgreSQL を起動して使う。用意できなければ従来どおりスキップされる。
    """
    global TEST_DATABASE_URL
    if TEST_DATABASE_URL or not os.environ.get("CI"):
        return

    from tests._ci_database import provision

    url = provision()
    if url is None:
        print("\n[conftest] CI用のPostgreSQLを用意できませんでした。DBテストはスキップします。")
        return

    os.environ["TEST_DATABASE_URL"] = url
    TEST_DATABASE_URL = url
    print(f"\n[conftest] CI用のPostgreSQLを用意しました（{url.rsplit('/', 1)[-1]}）。DBテストを実行します。")


def pytest_configure(config):
    """CI ではスイート全体を実行する。

    `.github/workflows/backend-ci.yml` はテストファイルを**5つ名指し**で
    実行しており、スイートの1%未満しか動いていない。追加した回帰テスト
    （テナント分離・監査ログ・パスワード保存・CSVインジェクション等）は
    どれもCIで実行されず、緑のチェックがそれらの防御を保証しない。

    ワークフローの修正案は docs/ci/backend-ci-db-tests.md にあるが、
    GitHub App に `workflows` 権限が無く自動では適用できないため、
    暫定措置としてここで収集対象を広げる。

    **ワークフローを直したらこのフックは削除すること。**

    ローカルでのファイル指定実行を邪魔しないよう、CI 環境変数がある時だけ
    働かせる。何が起きたかはログに明示する（5ファイルを指定したのに
    1500件走る理由が分からないと調査を妨げるため）。
    """
    _provision_ci_database()

    if not os.environ.get("CI"):
        return
    if config.args and all(pathlib.Path(a).resolve() == pathlib.Path(TESTS_DIR).resolve() for a in config.args):
        return
    print(
        f"\n[conftest] CI のため収集対象を {config.args} から tests/ 全体に広げます "
        f"(理由: backend-ci.yml がテストファイルを名指ししているため。"
        f"docs/ci/backend-ci-db-tests.md を参照)"
    )
    config.args = [TESTS_DIR]


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


@pytest_asyncio.fixture
async def api_client(db_session, monkeypatch):
    """アプリ全体をASGI経由で叩くクライアント。

    HTTP経路のテストを書くために2点を整える。

    1. ミドルウェア（監査ログ・冪等性・IP制限）は**モジュール読み込み時の
       グローバルなエンジン**を掴んでいる。テストは別のイベントループで動くため、
       そのままでは「別ループのFuture」エラーになり、本来の応答が握り潰される。
       テスト用セッションに差し替えてループを揃える。
    2. レート制限はプロセス内にカウンタを持つ。スイート全体では同じクライアントIPから
       大量に叩くことになり、後から動くテストだけが 429 で落ちる（順序依存）。
       テストごとにカウンタを空にする。
    """
    import contextlib

    import httpx
    from httpx import ASGITransport

    from app.core.database import get_db
    from app.main import app
    from app.middleware import audit_log, idempotency, ip_restriction

    @contextlib.asynccontextmanager
    async def _test_session():
        # セッションの close はテスト側が管理するので、ここでは呼ばない。
        yield db_session

    for module in (audit_log, idempotency, ip_restriction):
        monkeypatch.setattr(module, "async_session_factory", _test_session)

    # 上限はミドルウェアのインスタンスに保持されるため、クラス属性を書き換えても
    # 効かない。dispatch を素通しにして、スイート全体での積み上がりを断つ。
    from app.middleware.rate_limit import RateLimitMiddleware

    async def _passthrough(self, request, call_next):
        return await call_next(request)

    monkeypatch.setattr(RateLimitMiddleware, "dispatch", _passthrough)

    app.dependency_overrides[get_db] = lambda: db_session
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
