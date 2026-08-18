"""パスパラメータのルートに隠れて到達不能になっているルートが無いことの検証。

FastAPI は宣言順にマッチするため、`GET /{account_id}` を先に宣言すると、
あとから宣言した `GET /tax-rules` には**一生到達しない**。"tax-rules" を
UUID として解釈しようとして 422 を返すだけで、エラーにも警告にもならないため
気付きにくい（実際にこの形で1本が死んでいた）。

新しいエンドポイントを足したときに同じことが起きないよう、
「文字列のルートが、先に宣言された同形のパラメータ付きルートに
隠されていないこと」をルーティングから検査する。
"""
import re

import pytest
from fastapi.routing import APIRoute

from app.main import app

_PARAM = re.compile(r"\{[^}]+\}")


def _segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _shadows(pattern: list[str], literal: list[str]) -> bool:
    """`pattern` が `literal` を飲み込むか（同じ長さで、差はパラメータ部分だけ）。"""
    if len(pattern) != len(literal):
        return False
    for p, lit in zip(pattern, literal, strict=True):
        if _PARAM.fullmatch(p):
            continue
        if p != lit:
            return False
    return True


def _shadowed_routes() -> list[tuple[str, str, str]]:
    """(メソッド, 隠されたパス, 隠しているパス) の一覧。"""
    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    found = []
    for index, route in enumerate(routes):
        literal = _segments(route.path)
        if any(_PARAM.fullmatch(s) for s in literal):
            continue  # パラメータ付きルート自身は対象外
        for earlier in routes[:index]:
            if not (route.methods & earlier.methods):
                continue
            pattern = _segments(earlier.path)
            if not any(_PARAM.fullmatch(s) for s in pattern):
                continue
            if _shadows(pattern, literal):
                found.append((",".join(sorted(route.methods)), route.path, earlier.path))
                break
    return found


def test_routes_were_discovered():
    """検査対象が取れないまま「問題なし」になっていないこと。"""
    assert len([r for r in app.routes if isinstance(r, APIRoute)]) > 100


def test_no_route_is_shadowed():
    shadowed = _shadowed_routes()
    detail = "\n".join(f"  {m} {path} が {by} に隠れている" for m, path, by in shadowed)
    assert not shadowed, (
        "先に宣言されたパラメータ付きルートに隠れて到達できないルートがある:\n"
        f"{detail}\n"
        "文字列のルートをパラメータ付きルートより前に宣言すること。"
    )


@pytest.mark.parametrize(
    ("pattern", "literal", "expected"),
    [
        (["masters", "{account_id}"], ["masters", "tax-rules"], True),
        (["masters", "{account_id}"], ["masters", "sub-accounts", "x"], False),
        (["masters", "{a}", "lines"], ["masters", "x", "lines"], True),
        (["masters", "{a}"], ["other", "tax-rules"], False),
    ],
)
def test_shadow_detection_logic(pattern, literal, expected):
    """判定ロジック自体が機能していること。"""
    assert _shadows(pattern, literal) is expected
