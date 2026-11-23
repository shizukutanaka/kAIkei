#!/usr/bin/env python3
"""kAIkei 個人用単体パッケージ（Windows）の組み立てスクリプト。

使い方:
    python3 packaging/build_package.py

成果物（dist/ は .gitignore 済みのためコミットされない）:
    dist/kaikei-windows/      展開済みパッケージ
    dist/kaikei-windows.zip   配布用 ZIP

中身:
    runtime/python/  Python 3.12.8 埋め込み版（python.org 公式 ZIP を
                     SHA256 で検証して使用）+ 依存ライブラリ一式。
                     依存は pip の --platform 指定で Windows 用ホイールを
                     集めるため、このスクリプト自体は Windows 以外でも
                     実行できる（Windows 実機での起動確認は別途必要）。
    server/          バックエンドの app パッケージ
    web/             画面の静的書き出し（NEXT_OUTPUT=export でビルド）
    launch.py / START-KAIKEI.bat / README.txt

依存の絞り込み（backend/requirements.txt からの変更点はこの2つだけ）:
    - 開発専用（pytest / ruff / mypy 等）は入れない
    - uvicorn は [standard] 拡張なしにする（uvloop 等の Windows で
      使えない加速部品を避ける。uvicorn 自体の動作は変わらない）
"""

import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PKG = DIST / "kaikei-windows"
CACHE = DIST / ".cache"

PYTHON_VERSION = "3.12.8"
EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
EMBED_SHA256 = "8d3f33be9eb810f23c102f08475af2854e50484b8e4e06275e937be61ce3d2fb"

DEV_ONLY_PREFIXES = ("pytest", "ruff", "mypy")


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)


def download_embed_python() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    if archive.is_file() and hashlib.sha256(archive.read_bytes()).hexdigest() == EMBED_SHA256:
        print(f"Python 埋め込み版はキャッシュ済み: {archive}")
        return archive
    print(f"ダウンロード: {EMBED_URL}")
    urllib.request.urlretrieve(EMBED_URL, archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != EMBED_SHA256:
        raise SystemExit(f"SHA256 が一致しません: {digest} != {EMBED_SHA256}")
    return archive


def package_requirements() -> Path:
    """backend/requirements.txt からパッケージ用依存リストを生成する。"""
    lines = []
    for raw in (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8").splitlines():
        name = raw.split("==")[0].split(">=")[0].split("[")[0].strip().lower()
        if name.startswith(DEV_ONLY_PREFIXES):
            continue
        lines.append(raw.replace("uvicorn[standard]", "uvicorn"))
    out = CACHE / "requirements-package.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def install_windows_wheels(site_packages: Path, requirements: Path) -> None:
    """Windows 用ホイールだけを site-packages へ集める（実行はしない）。"""
    # pip の一時展開先は dist 配下に寄せる（/tmp が小さい環境でも組み立てられる）。
    tmp_dir = CACHE / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TMPDIR=str(tmp_dir))
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--target",
            str(site_packages),
            "--platform",
            "win_amd64",
            "--python-version",
            "312",
            "--implementation",
            "cp",
            "--abi",
            "cp312",
            "--only-binary=:all:",
            "-r",
            str(requirements),
        ],
        env=env,
    )
    # python -m uvicorn で起動するため、コンソールスクリプト置き場は不要。
    shutil.rmtree(site_packages / "bin", ignore_errors=True)
    for pycache in site_packages.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)


def build_frontend() -> Path:
    frontend = ROOT / "frontend"
    if not (frontend / "node_modules").is_dir():
        run(["npm", "ci"], cwd=frontend)
    env = dict(os.environ)
    env.update(
        {
            "NEXT_OUTPUT": "export",
            "NEXT_PUBLIC_API_URL": "",
            "NEXT_PUBLIC_API_BASE_URL": "/api/v1",
        }
    )
    run(["npx", "next", "build"], cwd=frontend, env=env)
    return frontend / "out"


def main() -> None:
    if PKG.exists():
        shutil.rmtree(PKG)
    (PKG / "runtime" / "python").mkdir(parents=True)

    # 1. 同梱 Python と依存ライブラリ
    archive = download_embed_python()
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(PKG / "runtime" / "python")
    pth = PKG / "runtime" / "python" / f"python{PYTHON_VERSION.replace('.', '')[:3]}._pth"
    pth.write_text(
        "python312.zip\n.\nLib\\site-packages\n..\\..\\server\nimport site\n",
        encoding="ascii",
    )
    install_windows_wheels(PKG / "runtime" / "python" / "Lib" / "site-packages", package_requirements())

    # 2. バックエンド本体
    shutil.copytree(
        ROOT / "backend" / "app",
        PKG / "server" / "app",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    # 3. 画面（静的書き出し）
    shutil.copytree(build_frontend(), PKG / "web")

    # 4. 起動まわり
    shutil.copy2(ROOT / "packaging" / "launch.py", PKG / "launch.py")
    shutil.copy2(ROOT / "packaging" / "START-KAIKEI.bat", PKG / "START-KAIKEI.bat")
    shutil.copy2(ROOT / "packaging" / "README-package.txt", PKG / "README.txt")

    # 5. ZIP 化
    zip_path = shutil.make_archive(str(DIST / "kaikei-windows"), "zip", root_dir=DIST, base_dir="kaikei-windows")

    total = sum(p.stat().st_size for p in PKG.rglob("*") if p.is_file())
    print(f"完成: {PKG}（{total / 1e6:.0f} MB）")
    print(f"ZIP:  {zip_path}（{Path(zip_path).stat().st_size / 1e6:.0f} MB）")


if __name__ == "__main__":
    main()
