"""個人用単体モード（SQLite + 同梱画面）の回帰テスト。

単体モードは mi 本人の PC で Docker も DB サーバも無しに動かすための形態で、
壊れてもサーバ構成のテスト（PostgreSQL 前提）では検出できない。ここでは
実ファイルの SQLite に対して、サーバ構成と同じ接合部（エンジン生成・
スキーマ作成・JSONB/UUID の往復・外部キー）が単体でも成立することを固定する。

PostgreSQL 側の振る舞いを変えていないこともあわせて確認する:
- JSONB は PostgreSQL で従来どおり JSONB に、SQLite では JSON にコンパイルされる
- PostgreSQL 用エンジンのプール設定は従来どおり
"""
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.schema import CreateTable

import app.models.models  # noqa: F401  -- 全テーブルを Base.metadata に登録する
from app.core.config import Settings
from app.core.database import Base, create_app_engine
from app.models.models import Company, Tenant, User
from app.standalone import init_schema_if_sqlite, resolve_web_file


def _sqlite_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path}/data/kaikei.db"


async def test_sqlite_engine_creates_schema_and_roundtrips(tmp_path):
    """単体モードの接合部: スキーマ作成→登録→読み戻しが実ファイルで通ること。"""
    engine = create_app_engine(_sqlite_url(tmp_path))
    try:
        assert await init_schema_if_sqlite(engine) is True

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            tenant = Tenant(tenant_name="単体", tenant_code="SOLO")
            session.add(tenant)
            await session.flush()
            user = User(
                tenant_id=tenant.tenant_id,
                email="solo@example.com",
                password_hash="x",
                display_name="本人",
                role="admin",
                mfa_backup_codes=[{"hash": "abc", "used": False}],
            )
            company = Company(tenant_id=tenant.tenant_id, company_name="個人事業", company_code="SOLO1")
            session.add_all([user, company])
            await session.commit()

        async with factory() as session:
            loaded = (await session.execute(select(User))).scalar_one()
            assert loaded.mfa_backup_codes == [{"hash": "abc", "used": False}]
            assert isinstance(loaded.user_id, uuid.UUID)
            assert loaded.created_at is not None
    finally:
        await engine.dispose()


async def test_sqlite_engine_enforces_foreign_keys(tmp_path):
    """SQLite でも外部キーが効くこと（PostgreSQL と同じ整合性の前提を守る）。"""
    engine = create_app_engine(_sqlite_url(tmp_path))
    try:
        await init_schema_if_sqlite(engine)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            session.add(Company(tenant_id=uuid.uuid4(), company_name="宙に浮いた会社", company_code="BAD"))
            with pytest.raises(IntegrityError):
                await session.commit()
    finally:
        await engine.dispose()


async def test_sqlite_engine_enables_foreign_key_pragma(tmp_path):
    engine = create_app_engine(_sqlite_url(tmp_path))
    try:
        async with engine.connect() as conn:
            enabled = (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one()
        assert enabled == 1
    finally:
        await engine.dispose()


async def test_init_schema_if_sqlite_ignores_postgres():
    """サーバ構成では起動時スキーマ作成をしないこと（Alembic の担当）。"""
    engine = create_app_engine("postgresql+asyncpg://kaikei:kaikei_dev@localhost:5432/kaikei")
    try:
        assert await init_schema_if_sqlite(engine) is False
    finally:
        await engine.dispose()


def test_postgres_engine_keeps_pool_settings():
    """サーバ構成のプール設定が従来どおりであること（単体対応で変えていない）。"""
    engine = create_app_engine("postgresql+asyncpg://kaikei:kaikei_dev@localhost:5432/kaikei")
    try:
        assert engine.url.get_dialect().name == "postgresql"
        assert engine.sync_engine.pool.size() == 20
    finally:
        import asyncio

        asyncio.run(engine.dispose())


def test_jsonb_compiles_to_jsonb_on_postgres_and_json_on_sqlite():
    """JSONB の二重コンパイル: 本番 DDL は不変、SQLite では JSON になる。"""
    table = Base.metadata.tables["users"]
    pg_ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    sqlite_ddl = str(CreateTable(table).compile(dialect=sqlite.dialect()))
    assert "mfa_backup_codes JSONB" in pg_ddl
    assert "JSONB" not in sqlite_ddl
    assert "mfa_backup_codes JSON" in sqlite_ddl


def test_settings_web_dir_path(tmp_path):
    """WEB_DIR は実在するディレクトリのときだけ配信元になる。"""
    assert Settings(WEB_DIR="").web_dir_path is None
    assert Settings(WEB_DIR=str(tmp_path / "missing")).web_dir_path is None
    assert Settings(WEB_DIR=str(tmp_path)).web_dir_path == tmp_path


def _build_web_dir(tmp_path):
    web = tmp_path / "web"
    (web / "_next" / "static").mkdir(parents=True)
    (web / "journals").mkdir()
    (web / "index.html").write_text("HOME", encoding="utf-8")
    (web / "bank.html").write_text("BANK", encoding="utf-8")
    (web / "bank.txt").write_text("BANK-FLIGHT", encoding="utf-8")
    (web / "journals" / "new.html").write_text("NEW", encoding="utf-8")
    (web / "journals" / "_.html").write_text("DETAIL", encoding="utf-8")
    (web / "journals" / "_.txt").write_text("DETAIL-FLIGHT", encoding="utf-8")
    (web / "_next" / "static" / "chunk.js").write_text("JS", encoding="utf-8")
    return web


def test_resolve_web_file(tmp_path):
    web = _build_web_dir(tmp_path)

    assert resolve_web_file(web, "") == web / "index.html"
    assert resolve_web_file(web, "bank") == web / "bank.html"
    assert resolve_web_file(web, "bank.txt") == web / "bank.txt"
    assert resolve_web_file(web, "_next/static/chunk.js") == web / "_next" / "static" / "chunk.js"
    # 実在する静的ルートはプレースホルダより優先される
    assert resolve_web_file(web, "journals/new") == web / "journals" / "new.html"
    # 動的ルートはプレースホルダの書き出しへ寄せる（HTML・フライトデータとも）
    assert resolve_web_file(web, f"journals/{uuid.uuid4()}") == web / "journals" / "_.html"
    assert resolve_web_file(web, f"journals/{uuid.uuid4()}.txt") == web / "journals" / "_.txt"
    # 拡張子の無い未知パスは SPA フォールバック、拡張子のある欠落ファイルは 404
    assert resolve_web_file(web, "some/client/route") == web / "index.html"
    assert resolve_web_file(web, "missing.js") is None
    # web_dir の外は配信しない
    assert resolve_web_file(web, "../secret.txt") is None


def test_mount_web_ui_serves_pages_and_keeps_api_404(tmp_path):
    """マウントしたアプリで画面が開き、API の未定義パスは JSON の 404 のまま。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.standalone import mount_web_ui

    web = _build_web_dir(tmp_path)
    mini = FastAPI()
    mount_web_ui(mini, web)

    with TestClient(mini) as client:
        assert client.get("/").text == "HOME"
        assert client.get("/bank").text == "BANK"
        assert client.get(f"/journals/{uuid.uuid4()}").text == "DETAIL"
        api_miss = client.get("/api/v1/does-not-exist")
        assert api_miss.status_code == 404
        assert api_miss.json() == {"detail": "Not Found"}


def test_main_app_has_no_web_ui_route_by_default():
    """サーバ構成（WEB_DIR 未設定）では画面配信ルートが存在しないこと。"""
    from app.main import app

    assert all(route.path != "/{full_path:path}" for route in app.routes)


def test_setup_page_only_until_first_user(tmp_path, monkeypatch):
    """初回設定ページは利用者ゼロの間だけ開き、できたらトップへ閉じること。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.standalone as standalone
    from app.standalone import mount_web_ui

    web = _build_web_dir(tmp_path)
    mini = FastAPI()
    mount_web_ui(mini, web)

    async def _zero():
        return 0

    async def _one():
        return 1

    with TestClient(mini, follow_redirects=False) as client:
        monkeypatch.setattr(standalone, "_count_users", _zero)
        page = client.get("/standalone-setup")
        assert page.status_code == 200
        assert "初回設定" in page.text

        monkeypatch.setattr(standalone, "_count_users", _one)
        closed = client.get("/standalone-setup")
        assert closed.status_code == 307
        assert closed.headers["location"] == "/"
