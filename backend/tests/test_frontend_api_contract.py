"""フロントエンドが呼ぶAPIが、実際にバックエンドに存在することの検証。

画面から呼んでいるパスが存在しなくても、誰かがその画面を開くまで誰も気付かない。
型検査もビルドも文字列の中身までは見ないため、エンドポイントの改名・移動・削除は
静かに壊れる。実際にこのリポジトリでは、パスパラメータ付きルートに隠れて
到達不能になっていたエンドポイントが2本あった。

ここでは frontend の `apiGet/apiPost/...` の第1引数を集め、FastAPI が
実際に公開しているルートと突き合わせる。テンプレートリテラルの補間
(`${id}`) はパスパラメータとみなす。
"""
import pathlib
import re

import pytest
from fastapi.routing import APIRoute

from app.main import app

FRONTEND_DIR = pathlib.Path(__file__).resolve().parents[2] / "frontend"
API_PREFIX = "/api/v1"

# 第1引数が文字列リテラル/テンプレートリテラルの呼び出しだけを対象にする。
_CALL = re.compile(
    r"""api(?:Get|Post|Put|Patch|Delete)\s*(?:<[^>]*>)?\(\s*(`[^`]*`|"[^"]*"|'[^']*')""",
)
_INTERPOLATION = re.compile(r"\$\{[^}]*\}")
_PARAM = re.compile(r"\{[^}]*\}")


def _segments(path: str) -> list[str]:
    """クエリ文字列を落として、パスをセグメントに分解する。"""
    return [s for s in path.split("?", 1)[0].split("/") if s]


def _backend_routes() -> list[list[str]]:
    return [
        _segments(_PARAM.sub("{}", route.path.removeprefix(API_PREFIX)))
        for route in app.routes
        if isinstance(route, APIRoute)
    ]


def _matches(call: list[str], route: list[str]) -> bool:
    """セグメント単位で照合する。

    フロント側の `${...}` は、パスパラメータのこともあれば
    （`/approvals/${action}` のように）固定セグメントを組み立てていることもある。
    静的には区別できないので、どちらの `{}` も「任意の1セグメント」として扱う。
    改名や削除は長さ・固定部分の不一致として検出できる。
    """
    if len(call) != len(route):
        return False
    return all(c == "{}" or r == "{}" or c == r for c, r in zip(call, route, strict=True))


def _frontend_calls() -> dict[str, list[str]]:
    """呼び出しパス -> それが書かれているファイルの一覧。"""
    calls: dict[str, list[str]] = {}
    for path in FRONTEND_DIR.rglob("*.ts*"):
        if "node_modules" in path.parts or path.name.endswith(".test.tsx"):
            continue
        for literal in _CALL.findall(path.read_text()):
            raw = literal[1:-1]
            if not raw.startswith("/"):
                continue  # 変数から組み立てているものは静的には追えない
            normalized = "/" + "/".join(_segments(_INTERPOLATION.sub("{}", raw)))
            calls.setdefault(normalized, []).append(str(path.relative_to(FRONTEND_DIR)))
    return calls


pytestmark = pytest.mark.skipif(not FRONTEND_DIR.is_dir(), reason="frontend ディレクトリが無い")


def test_calls_were_discovered():
    """抽出に失敗したまま「問題なし」になっていないこと。"""
    assert len(_frontend_calls()) > 50


def test_every_frontend_call_hits_a_real_endpoint():
    routes = _backend_routes()
    missing = {
        call: files
        for call, files in _frontend_calls().items()
        if not any(_matches(_segments(call), route) for route in routes)
    }
    detail = "\n".join(f"  {call}  <- {', '.join(sorted(set(files)))}" for call, files in sorted(missing.items()))
    assert not missing, (
        "フロントエンドが存在しないAPIを呼んでいる（改名・削除の取り残し）:\n"
        f"{detail}"
    )


def test_detection_logic_works():
    """判定ロジック自体が機能していること。"""
    # 補間・パスパラメータ・クエリ文字列の正規化
    assert _segments("/budgets/${id}/variance?x=1") == ["budgets", "${id}", "variance"]
    assert _INTERPOLATION.sub("{}", "/budgets/${id}/variance") == "/budgets/{}/variance"

    # 一致するもの
    assert _matches(["budgets", "{}", "variance"], ["budgets", "{}", "variance"])
    assert _matches(["approvals", "{}"], ["approvals", "approve"])
    # 一致しないもの（改名・階層違い）を通さないこと
    assert not _matches(["budgest", "{}"], ["budgets", "{}"])
    assert not _matches(["budgets"], ["budgets", "{}"])
