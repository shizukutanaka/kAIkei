"""個人用単体モードの補助（SQLite スキーマ初期化・同梱画面の配信・初回設定）。

単体モードは「DATABASE_URL が SQLite」かつ「WEB_DIR に画面一式が実在する」
場合にだけ有効になる。サーバ構成（PostgreSQL + Alembic + 別配信の画面）
ではこのモジュールの処理は一切走らない。

- スキーマ: 単体モードには Alembic の実行環境が無いため、起動時に
  `Base.metadata.create_all` で用意する（冪等。既存ファイルは壊さない）。
  モデルとマイグレーションの一致は DB テスト（test_migration_parity_db）が
  PostgreSQL 側で保証している。
- 画面配信: 書き出し済みの静的ファイルを API と同じオリジンで返す。
  API ルートの登録後にマウントされるため、/api/v1 配下は API が優先される。
- 初回設定: 製品の画面にはアカウント登録画面が無い（サーバ構成では管理側が
  API で作る前提）。単体モードでは利用者がまだ誰もいない間だけ
  /standalone-setup に設定ページを出し、既存の登録 API へ橋渡しする。
  利用者が1人でもできたら設定ページは閉じる。
"""

import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncEngine

SETUP_PATH = "standalone-setup"


async def init_schema_if_sqlite(engine: AsyncEngine) -> bool:
    """SQLite エンジンのときだけスキーマを作成し、True を返す。"""
    if engine.url.get_dialect().name != "sqlite":
        return False

    import app.models.models  # noqa: F401  -- 全テーブルを Base.metadata に登録する
    from app.core.database import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return True


async def _count_users() -> int:
    """登録済み利用者の数（初回設定ページを出すかどうかの判定用）。"""
    from sqlalchemy import func, select

    from app.core.database import async_session_factory
    from app.models.models import User

    async with async_session_factory() as session:
        return (await session.execute(select(func.count()).select_from(User))).scalar_one()


def resolve_web_file(web_dir: Path, url_path: str) -> Path | None:
    """URL パスに対応する静的ファイルを返す。配信すべきでない場合は None。

    書き出し（Next.js の output: "export"）の構造に合わせた解決順:
    1. そのままのファイル（_next 資産・*.txt のフライトデータ等）
    2. `<path>.html`（各画面）/ `<path>/index.html`
    3. 動的ルート /journals/[id] はプレースホルダ "_" の書き出しへ寄せる
       （ID は UUID 形式で "_" と衝突しない。frontend の generateStaticParams 参照）
    4. 拡張子の無いパスは画面遷移とみなし index.html（SPA フォールバック）
       拡張子のあるパスは fallback しない（HTML を JS/CSS と偽って返さない）
    """
    root = web_dir.resolve()
    rel = url_path.strip("/")
    if not rel:
        index = root / "index.html"
        return index if index.is_file() else None

    direct = (root / rel).resolve()
    if not direct.is_relative_to(root):
        return None  # web_dir の外（パストラバーサル）は配信しない
    if direct.is_file():
        return direct

    for candidate in (root / f"{rel}.html", root / rel / "index.html"):
        if candidate.is_file():
            return candidate

    parts = rel.split("/")
    if len(parts) == 2 and parts[0] == "journals":
        placeholder = root / "journals" / ("_.txt" if parts[1].endswith(".txt") else "_.html")
        if placeholder.is_file():
            return placeholder

    if "." in parts[-1]:
        return None

    index = root / "index.html"
    return index if index.is_file() else None


_SETUP_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>kAIkei 初回設定</title>
<style>
  body { font-family: sans-serif; margin: 2rem auto; max-width: 32rem; padding: 0 1rem; }
  label { display: block; margin-top: 1rem; font-weight: bold; }
  input { width: 100%; padding: 0.5rem; margin-top: 0.25rem; box-sizing: border-box; }
  button { margin-top: 1.5rem; padding: 0.6rem 1.2rem; font-size: 1rem; }
  .note { color: #555; font-size: 0.9rem; }
  #message { margin-top: 1rem; white-space: pre-wrap; }
</style>
</head>
<body>
<h1>kAIkei 初回設定</h1>
<p>最初に、あなた専用のアカウントを作ります。この設定は利用者がまだ
誰もいないときだけ表示されます。</p>
<form id="setup">
  <label>メールアドレス<input id="email" type="email" required></label>
  <label>パスワード（8文字以上）<input id="password" type="password" required minlength="8"></label>
  <label>表示名<input id="display_name" required></label>
  <label>組織コード<input id="tenant_code" value="personal" required></label>
  <p class="note">組織コードは自分のための目印です。初期値のままで構いません。</p>
  <button type="submit">アカウントを作る</button>
</form>
<p id="message"></p>
<script>
document.getElementById("setup").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.getElementById("message");
  const payload = {
    email: document.getElementById("email").value,
    password: document.getElementById("password").value,
    display_name: document.getElementById("display_name").value,
    tenant_code: document.getElementById("tenant_code").value,
  };
  const response = await fetch("/api/v1/auth/register", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  if (response.ok) {
    message.textContent = "アカウントを作りました。ログイン画面へ移動します…";
    setTimeout(() => { location.href = "/login"; }, 1000);
  } else {
    const data = await response.json().catch(() => ({}));
    message.textContent = "作れませんでした: " + (data.detail || response.status);
  }
});
</script>
</body>
</html>
"""


def mount_web_ui(app: FastAPI, web_dir: Path) -> None:
    """同梱画面の配信をアプリに足す（API ルート登録後に呼ぶこと）。"""

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    async def _serve_web_ui(full_path: str) -> Response:
        if full_path.startswith("api/"):
            # API の未定義パスを画面で誤魔化さない（呼び出し側が 404 を判定できる）。
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        if full_path == SETUP_PATH:
            if await _count_users() > 0:
                return RedirectResponse(url="/")
            return HTMLResponse(content=_SETUP_HTML)
        target = resolve_web_file(web_dir, full_path)
        if target is None:
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return FileResponse(target, media_type=media_type)
