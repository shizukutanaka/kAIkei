import os
from collections.abc import AsyncGenerator

from sqlalchemy import event, make_url
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001, ANN202
    """SQLite には JSONB 型が無いため、単体モードでは JSON として作成する。

    PostgreSQL では従来どおり JSONB でコンパイルされる（このフックは sqlite
    方言にだけ効く）。値の読み書きはどちらの方言でも SQLAlchemy の JSON 系
    型が担うため、アプリケーションから見た振る舞いは変わらない。
    """
    return "JSON"


def _is_sqlite_url(database_url: str) -> bool:
    return make_url(database_url).get_dialect().name == "sqlite"


def _ensure_sqlite_file_dir(database_url: str) -> None:
    """SQLite ファイルの置き場所が無ければ作る（初回起動で失敗させない）。"""
    database = make_url(database_url).database
    if not database or database == ":memory:":
        return
    parent = os.path.dirname(os.path.abspath(database))
    os.makedirs(parent, exist_ok=True)


def create_app_engine(database_url: str) -> AsyncEngine:
    """DATABASE_URL に応じたエンジンを作る。

    PostgreSQL（サーバ構成）は従来どおりのコネクションプール設定。
    SQLite（個人用単体モード）はプール引数が意味を持たないため分け、
    あわせて外部キー制約を有効化する（SQLite は既定で無効だが、
    PostgreSQL と同じ整合性の前提でサービス層が書かれているため）。
    """
    if _is_sqlite_url(database_url):
        _ensure_sqlite_file_dir(database_url)
        sqlite_engine = create_async_engine(
            database_url,
            echo=False,
            connect_args={"timeout": 30},
        )

        @event.listens_for(sqlite_engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):  # noqa: ANN001, ANN202
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return sqlite_engine

    return create_async_engine(
        database_url,
        echo=False,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
    )


engine = create_app_engine(settings.DATABASE_URL)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
