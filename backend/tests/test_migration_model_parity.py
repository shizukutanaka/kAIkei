"""Regression guard: every ORM model table must have a creating migration.

Models are declared on Base.metadata, but the test harness builds its schema via
Base.metadata.create_all — so a model whose table has no Alembic migration still
passes every test yet is MISSING from a migration-built production database.
This exact gap hid the `notifications` / `notification_preferences` tables until
migration 0025. This test fails fast if any future model reintroduces the gap.
"""
import pathlib
import re

import app.models.models  # noqa: F401 -- registers all tables on Base.metadata
from app.core.database import Base

_VERSIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "app" / "migrations" / "versions"
# `op.create_table(` followed (possibly across a newline) by the quoted table name.
_CREATE_TABLE_RE = re.compile(r"op\.create_table\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']")


def _tables_created_by_migrations() -> set[str]:
    created: set[str] = set()
    for path in _VERSIONS_DIR.glob("*.py"):
        created.update(_CREATE_TABLE_RE.findall(path.read_text(encoding="utf-8")))
    return created


def test_every_model_table_has_a_creating_migration():
    model_tables = set(Base.metadata.tables)
    created = _tables_created_by_migrations()
    missing = sorted(model_tables - created)
    assert not missing, (
        "These ORM tables have no `op.create_table` in any migration, so "
        "`alembic upgrade head` will not create them in production: " + ", ".join(missing)
    )


def test_migration_directory_is_discoverable():
    # Guards against the test silently passing because it found no migrations at all.
    assert _tables_created_by_migrations(), "No create_table calls found — migrations dir path is wrong?"
