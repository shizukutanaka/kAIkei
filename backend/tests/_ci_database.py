"""CI で PostgreSQL を自前で用意する（ワークフローを編集せずに）。

DBを要するテストは `TEST_DATABASE_URL` が無いとスキップされる。CI では設定が
無いため、テナント分離・給与・消費税といった**金額と権限に直結する174件**が
一度も実行されていなかった。

本来は `.github/workflows/backend-ci.yml` に Postgres サービスを足すのが筋だが、
GitHub App に `workflows` 権限が無く自動適用できない（push が拒否されることを
実測済み）。一方 GitHub の ubuntu ランナーには **PostgreSQL が導入済みで停止
している**ので、こちら側で起動して用意すればワークフローに触れずに済む。

失敗したら黙って諦める。用意できなければ従来どおりスキップされるだけで、
CI を壊すことはない。**ワークフローを直したらこのモジュールは削除すること。**
"""
from __future__ import annotations

import os
import shutil
import subprocess

# ローカル開発で使うロール名とは意図的に分ける。同名だと、CI用に
# パスワードを設定し直した際に手元の設定を壊しうる。
ROLE = "kaikei_ci"
PASSWORD = "kaikei_ci"
DATABASE = "kaikei_ci_test"
PORT = "5432"


def _run(args: list[str], timeout: int = 60) -> bool:
    """コマンドを実行し、成功したかを返す。例外は握り潰す。"""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _psql_as_superuser(sql: str) -> bool:
    """postgres ロールで SQL を実行する。"""
    if _run(["sudo", "-n", "-u", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-c", sql]):
        return True
    # sudo が使えない環境（既に postgres ユーザー等）向けの直接実行。
    return _run(["psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-c", sql])


def _server_is_up() -> bool:
    if shutil.which("pg_isready") is None:
        return False
    return _run(["pg_isready", "-q", "-p", PORT], timeout=15)


def _start_server() -> bool:
    """停止している PostgreSQL を起動する。複数の起動方法を順に試す。"""
    if _server_is_up():
        return True
    for args in (
        ["sudo", "-n", "systemctl", "start", "postgresql"],
        ["sudo", "-n", "service", "postgresql", "start"],
        ["service", "postgresql", "start"],
    ):
        if _run(args) and _server_is_up():
            return True
    return _server_is_up()


def provision() -> str | None:
    """CI 用のDBを用意し、接続URLを返す。用意できなければ None。

    既に `TEST_DATABASE_URL` があれば何もしない（ローカルや、ワークフローで
    サービスを設定した場合を尊重する）。
    """
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    if not os.environ.get("CI"):
        return None
    if not _start_server():
        return None

    # 何度実行しても同じ状態になるようにする（再実行や、前回の残骸に備える）。
    # ロールが既にある場合もパスワードを設定し直す。作成のみだと、以前と違う
    # パスワードのロールが残っていたときに接続できない。
    _psql_as_superuser(
        f"DO $$BEGIN "
        f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{ROLE}') THEN "
        f"CREATE ROLE {ROLE} LOGIN SUPERUSER PASSWORD '{PASSWORD}'; "
        f"ELSE ALTER ROLE {ROLE} LOGIN SUPERUSER PASSWORD '{PASSWORD}'; "
        f"END IF; END$$;"
    )
    # 既にあれば失敗するが、それは想定内。用意できたかは接続で判断する。
    _psql_as_superuser(f'CREATE DATABASE "{DATABASE}" OWNER {ROLE};')

    url = f"postgresql+asyncpg://{ROLE}:{PASSWORD}@localhost:{PORT}/{DATABASE}"
    if not _can_connect(url):
        return None
    return url


def _can_connect(url: str) -> bool:
    """実際に接続できるかを確かめる。ここを省くと、用意できていないのに
    テストを実行してしまい、大量の接続エラーでCIが壊れる。"""
    try:
        import asyncio

        import asyncpg
    except ImportError:
        return False

    dsn = url.replace("postgresql+asyncpg://", "postgresql://")

    async def _check() -> bool:
        try:
            conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=15)
        except Exception:  # noqa: BLE001 -- 接続できない理由は問わない
            return False
        await conn.close()
        return True

    try:
        return asyncio.run(_check())
    except Exception:  # noqa: BLE001
        return False
