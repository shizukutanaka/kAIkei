"""Regression guard: no duplicate route definitions within an endpoint module.

統合(merge)時、同一パスのハンドラが複数のブランチから持ち込まれると、FastAPIは
最初に登録されたものだけを解決に使い、後続は到達不能な死にコードになる（権限や
レスポンス形が異なっていても気付けない）。実際に invoices.py の
GET /validate-registration-number が重複していた。静的に検出して再発を防ぐ。
"""
import collections
import pathlib
import re

_ENDPOINTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "app" / "api" / "v1" / "endpoints"
_ROUTE_RE = re.compile(r'@router\.(get|post|put|patch|delete)\(\s*"([^"]*)"')


def _duplicate_routes() -> dict[str, list[tuple[str, str, int]]]:
    dupes: dict[str, list[tuple[str, str, int]]] = {}
    for path in sorted(_ENDPOINTS_DIR.glob("*.py")):
        counts = collections.Counter(_ROUTE_RE.findall(path.read_text(encoding="utf-8")))
        found = [(method.upper(), route, n) for (method, route), n in counts.items() if n > 1]
        if found:
            dupes[path.name] = found
    return dupes


def test_no_duplicate_routes_within_module():
    dupes = _duplicate_routes()
    assert not dupes, (
        "同一モジュール内で重複したルート定義があります（後勝ちではなく先勝ちで "
        "後続は到達不能になります）: " + str(dupes)
    )


def test_scanner_actually_finds_routes():
    # ガードが空振り（ディレクトリ誤り等）で常にパスすることを防ぐ
    total = sum(
        len(_ROUTE_RE.findall(p.read_text(encoding="utf-8"))) for p in _ENDPOINTS_DIR.glob("*.py")
    )
    assert total > 50, f"エンドポイント走査が機能していない可能性 (found={total})"
