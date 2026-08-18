"""マイグレーションとモデル定義の一致検証。

テスト用DBは `Base.metadata.create_all` で作られるため、**マイグレーションは
テストで一度も実行されない**。モデルにカラムを足してマイグレーションを書き忘れても、
テストは全て通ってしまい、本番のデプロイで初めて壊れる（実際に一度起きている）。

そこで使い捨てのデータベースを作り、`alembic upgrade head` だけで組み上げた
スキーマがモデル定義と一致することを確認する。ついでにマイグレーションが
最後まで通ること自体の検証にもなる。
"""
import asyncio
import os
import re

import pytest

pytestmark = pytest.mark.db

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
_SCRATCH_SUFFIX = "_migration_check"


def _scratch_name(url: str) -> str:
    """検証用DB名。誤って本来のDBを消さないよう接尾辞で識別する。"""
    base = url.rsplit("/", 1)[-1].split("?")[0]
    return f"{base}{_SCRATCH_SUFFIX}"


def _admin_dsn(url: str) -> str:
    """asyncpg で maintenance DB に接続するためのDSN。"""
    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", url)
    return dsn.rsplit("/", 1)[0] + "/postgres"


async def _recreate_database(url: str, name: str) -> None:
    import asyncpg

    assert name.endswith(_SCRATCH_SUFFIX), f"想定外のDB名: {name}"
    conn = await asyncpg.connect(_admin_dsn(url))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _drop_database(url: str, name: str) -> None:
    import asyncpg

    assert name.endswith(_SCRATCH_SUFFIX), f"想定外のDB名: {name}"
    conn = await asyncpg.connect(_admin_dsn(url))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
    finally:
        await conn.close()


async def _reflect(url: str) -> tuple[set[str], dict[str, set[str]]]:
    from sqlalchemy import inspect
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            names = await conn.run_sync(lambda c: inspect(c).get_table_names())
            columns = {}
            for table in names:
                columns[table] = await conn.run_sync(
                    lambda c, t=table: {col["name"] for col in inspect(c).get_columns(t)}
                )
    finally:
        await engine.dispose()
    return set(names), columns


@pytest.fixture(scope="module")
def migrated_schema():
    """使い捨てDBにマイグレーションを流し、反映されたスキーマを返す。"""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")

    from alembic import command
    from alembic.config import Config

    from app.core.config import settings

    name = _scratch_name(TEST_DATABASE_URL)
    scratch_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/" + name

    try:
        asyncio.run(_recreate_database(TEST_DATABASE_URL, name))
    except Exception as exc:  # noqa: BLE001 -- 権限や接続の問題は環境要因
        pytest.skip(f"検証用データベースを作成できない: {exc}")
    original = settings.DATABASE_URL
    try:
        # alembic/env.py は settings.DATABASE_URL を読む。
        settings.DATABASE_URL = scratch_url
        command.upgrade(Config("alembic.ini"), "head")
        yield asyncio.run(_reflect(scratch_url))
    finally:
        settings.DATABASE_URL = original
        asyncio.run(_drop_database(TEST_DATABASE_URL, name))


def _model_schema() -> tuple[set[str], dict[str, set[str]]]:
    import app.models.models  # noqa: F401  -- 全テーブルを Base.metadata に登録する
    from app.core.database import Base

    tables = set(Base.metadata.tables)
    columns = {t: set(Base.metadata.tables[t].columns.keys()) for t in tables}
    return tables, columns


def test_migrations_apply_cleanly(migrated_schema):
    """`alembic upgrade head` が最後まで通り、テーブルが作られること。"""
    tables, _ = migrated_schema
    assert "alembic_version" in tables
    assert len(tables) > 20


def test_no_table_drift(migrated_schema):
    db_tables, _ = migrated_schema
    model_tables, _ = _model_schema()
    db_tables = db_tables - {"alembic_version"}

    missing = sorted(model_tables - db_tables)
    extra = sorted(db_tables - model_tables)
    assert not missing, f"モデルにあってマイグレーションに無いテーブル: {missing}"
    assert not extra, f"マイグレーションにあってモデルに無いテーブル: {extra}"


def test_no_column_drift(migrated_schema):
    db_tables, db_columns = migrated_schema
    model_tables, model_columns = _model_schema()

    problems = []
    for table in sorted(model_tables & (db_tables - {"alembic_version"})):
        missing = sorted(model_columns[table] - db_columns[table])
        extra = sorted(db_columns[table] - model_columns[table])
        if missing:
            problems.append(f"{table}: マイグレーション漏れ -> {missing}")
        if extra:
            problems.append(f"{table}: モデルに無い列 -> {extra}")
    assert not problems, "モデルとマイグレーションの差分:\n" + "\n".join(problems)
