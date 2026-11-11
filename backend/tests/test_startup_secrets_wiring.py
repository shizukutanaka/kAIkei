"""起動時シークレット検証の**配線**テスト。

`check_insecure_defaults` 自体の単体テストは `test_secrets_check.py` にあるが、
検出関数が正しくても、startup イベントがそれを呼ばなかったり、判定対象の
設定を渡し忘れたりすれば本番事故は防げない。実際 DATABASE_URL は検出対象に
含まれていながら `validate_secrets` が渡しておらず、本番でも開発用デフォルト
認証情報のまま静かに起動できる状態だった。

ここでは `validate_secrets` を実際に呼び、設定の組み合わせごとに
「本番では RuntimeError で起動拒否／本番以外では警告のみで継続」を assert する。
"""

import pytest

from app.core.config import settings
from app.core.secrets_check import DEV_DATABASE_URL
from app.main import validate_secrets

STRONG_SECRET = "x" * 40
CUSTOM_DATABASE_URL = "postgresql+asyncpg://kaikei:prod-password@db.internal:5432/kaikei"


def _use_strong_config(monkeypatch, *, environment: str, database_url: str) -> None:
    """DATABASE_URL 以外を本番でも安全な値に固定し、対象だけを差し替える。"""
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", STRONG_SECRET)
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "prod-key")
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "prod-secret")
    monkeypatch.setattr(settings, "CORS_ALLOW_ORIGINS", "https://kaikei.example.com")
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)


async def test_production_startup_refuses_default_database_url(monkeypatch):
    """本番で DATABASE_URL が開発用デフォルトのままなら起動を拒否すること。"""
    _use_strong_config(monkeypatch, environment="production", database_url=DEV_DATABASE_URL)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        await validate_secrets()


async def test_production_startup_allows_custom_database_url(monkeypatch):
    """本番でも DATABASE_URL が設定済みなら起動を継続すること（過検出しない）。"""
    _use_strong_config(monkeypatch, environment="production", database_url=CUSTOM_DATABASE_URL)

    await validate_secrets()


async def test_development_startup_only_warns_with_default_database_url(monkeypatch):
    """本番以外ではデフォルトのままでも起動を妨げないこと（ADR-011 の開発体験維持）。"""
    _use_strong_config(monkeypatch, environment="development", database_url=DEV_DATABASE_URL)

    await validate_secrets()
