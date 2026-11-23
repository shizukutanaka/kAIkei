#!/usr/bin/env python3
"""kAIkei 個人用単体パッケージの起動スクリプト（標準ライブラリのみ）。

START-KAIKEI.bat から同梱 Python（runtime/python）で呼ばれる前提だが、
通常の Python でも動く。サーバ本体はこのスクリプトが子プロセスとして
起動する uvicorn で、この窓が開いている間だけ kAIkei が動く。

やること:
  1. データ置き場（data/）を用意し、ログイン用の秘密鍵を初回だけ生成して
     data/ に保存する（2回目以降は同じ鍵を使い回すのでログインが切れない）。
  2. 候補ポートを順に調べる。応答が kAIkei 自身なら「起動済み」として
     画面を開くだけで終わる。他のアプリが応答するポートは飛ばす
     （ポートが重なったときに別アプリの画面を開いてしまう事故の防止）。
  3. 空いているポートでサーバを起動し、kAIkei の応答を確認してから
     ブラウザを開く。サーバが終わるまでこのスクリプトは待ち続ける。
"""

import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "kAIkei"  # バックエンドの /health が返すアプリ名（識別マーカー）
CANDIDATE_PORTS = [8000, 8001, 8002, 8003, 8080, 18000]
STARTUP_TIMEOUT_SECONDS = 90

HOME = Path(__file__).resolve().parent
SERVER_DIR = HOME / "server"
WEB_DIR = HOME / "web"
DATA_DIR = HOME / "data"


def log(message: str) -> None:
    print(f"[kAIkei] {message}", flush=True)


def probe(port: int) -> str:
    """ポートの状態を返す: "ours"（kAIkei が応答）/ "busy"（別の何か）/ "free"。"""
    url = f"http://127.0.0.1:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # DB 未接続でも /health は JSON を返す（503）。中身で自アプリか判定する。
        body = e.read().decode("utf-8", errors="replace")
    except OSError:
        return "free"
    try:
        return "ours" if json.loads(body).get("app") == APP_NAME else "busy"
    except ValueError:
        return "busy"


def prepare_data_dir() -> str:
    """data/ と JWT 秘密鍵を用意し、秘密鍵を返す。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    secret_file = DATA_DIR / ".jwt_secret"
    if secret_file.is_file():
        saved = secret_file.read_text(encoding="utf-8").strip()
        if len(saved) >= 32:
            return saved
    secret = secrets.token_hex(32)
    secret_file.write_text(secret, encoding="utf-8")
    log("初回起動: ログイン用の秘密鍵を data フォルダに作りました。")
    return secret


def server_env(jwt_secret: str) -> dict[str, str]:
    env = dict(os.environ)
    db_path = (DATA_DIR / "kaikei.db").resolve().as_posix()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    env["WEB_DIR"] = str(WEB_DIR)
    env["JWT_SECRET_KEY"] = jwt_secret
    env["ENVIRONMENT"] = "local"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(SERVER_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def start_url(port: int) -> str:
    """開くべき画面の URL。利用者がまだ誰もいなければ初回設定ページにする。"""
    base = f"http://127.0.0.1:{port}/"
    try:
        db_path = DATA_DIR / "kaikei.db"
        if db_path.is_file():
            conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
            try:
                (count,) = conn.execute("SELECT COUNT(*) FROM users").fetchone()
            finally:
                conn.close()
            if count == 0:
                return base + "standalone-setup"
    except Exception:
        pass  # 判定できなければ通常のトップ画面を開く（設定は画面側でも閉じている）
    return base


def wait_until_ours(port: int, proc: subprocess.Popen) -> bool:
    """起動したサーバが kAIkei として応答するまで待つ。"""
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        if probe(port) == "ours":
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not (SERVER_DIR / "app").is_dir() or not WEB_DIR.is_dir():
        log("エラー: パッケージの内容が不足しています（server / web フォルダが見つかりません）。")
        log("ZIP を展開し直してから、もう一度起動してください。")
        return 2

    jwt_secret = prepare_data_dir()
    log(f"データの置き場所: {DATA_DIR}")
    log("バックアップは data フォルダごとコピーするだけで済みます。")

    for port in CANDIDATE_PORTS:
        state = probe(port)
        if state == "ours":
            log(f"kAIkei は既に起動しています（ポート {port}）。画面を開きます。")
            webbrowser.open(start_url(port))
            return 0
        if state == "busy":
            log(f"ポート {port} は他のアプリが使っているため飛ばします。")
            continue

        log(f"ポート {port} でサーバを起動します…")
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=str(SERVER_DIR),
            env=server_env(jwt_secret),
        )
        if not wait_until_ours(port, proc):
            log("エラー: サーバが起動しませんでした。上のログを確認してください。")
            if proc.poll() is None:
                proc.terminate()
            return proc.returncode or 1

        url = start_url(port)
        log(f"起動しました: {url}")
        log("この窓を閉じると kAIkei は停止します。")
        webbrowser.open(url)
        try:
            return proc.wait()
        except KeyboardInterrupt:
            log("停止します…")
            proc.terminate()
            proc.wait()
            return 0

    log("エラー: 空いているポートが見つかりませんでした。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
