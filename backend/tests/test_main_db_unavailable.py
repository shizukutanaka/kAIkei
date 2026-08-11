"""DB接続断時のHTTP契約の回帰テスト（DB不要）。

修正前の挙動:
  - GET /health は DB 断でも 200 を返していた（縮退をLB/コンテナが検知不能）。
  - DB接続断で asyncpg の ConnectionRefusedError が素通りし、
    エンドポイントは本文なしの 500 Internal Server Error を返していた。

修正後: /health は 503、DBAPIError/OperationalError は JSON本文付き 503。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class _FailingEngine:
    def connect(self):  # noqa: D102
        raise OperationalError("SELECT 1", {}, ConnectionRefusedError("refused"))


def test_health_returns_503_when_db_down(client, monkeypatch):
    from app.core import database

    monkeypatch.setattr(database, "engine", _FailingEngine())
    resp = client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["database"] == "disconnected"


def test_health_returns_200_when_db_up(client, monkeypatch):
    class _OkConn:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, _stmt):
            return None

    class _OkEngine:
        def connect(self):
            return _OkConn()

    from app.core import database

    monkeypatch.setattr(database, "engine", _OkEngine())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["database"] == "connected"


def test_connection_refused_is_normalized_to_503(client):
    """asyncpg の生 ConnectionRefusedError も 503 に正規化される。

    これは DBAPIError にラップされず素通りしていた実際の本番シナリオ。
    """
    route = "/__test_conn_refused__"

    @app.get(route)
    async def _refuse() -> dict[str, str]:  # pragma: no cover - 例外送出のみ
        raise ConnectionRefusedError("connection refused")

    try:
        resp = client.get(route)
        assert resp.status_code == 503
        assert "detail" in resp.json()
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", None) != route
        ]


def test_dbapi_error_is_normalized_to_503(client):
    """任意のルートで DB 断が起きたら 500 ではなく JSON本文付き 503。"""
    route = "/__test_db_down__"

    @app.get(route)
    async def _boom() -> dict[str, str]:  # pragma: no cover - 例外送出のみ
        raise OperationalError("SELECT 1", {}, ConnectionRefusedError("refused"))

    try:
        resp = client.get(route)
        assert resp.status_code == 503
        assert "detail" in resp.json()
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", None) != route
        ]
