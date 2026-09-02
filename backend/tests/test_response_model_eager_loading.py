"""応答に含めるリレーションを遅延ロードのままにしていないことの検証。

非同期セッションではリレーションの遅延ロードが `MissingGreenlet` になる。
応答スキーマにリレーション由来のフィールド（`lines` 等）があるのに
eager load していないと、**そのエンドポイントは必ず 500 を返す**。

実際に仕訳の作成・取得・取消・一覧が全て壊れていた。会計システムの中核だが、
DBへ直接INSERTするテストばかりでHTTP経路を通していなかったため、
1,600件超が緑のまま気付かれなかった。

以前この種類を探したときは「関数本文にスキーマ名が出現するか」で判定して
おり、`response_model` をデコレータに書く仕訳系を取りこぼした。ここでは
ルーティングが実際に使う `response_model` から判定する。
"""
import inspect
import pathlib
import re

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.main import app

MODELS_FILE = pathlib.Path(__file__).resolve().parents[1] / "app" / "models" / "models.py"

# eager load していると判断する書き方。
_EAGER = ("selectinload", "joinedload", "subqueryload", "attribute_names")

# 意図的な例外。(パス, メソッド) -> 理由。
ALLOWED: dict[tuple[str, str], str] = {}


def _orm_relationships() -> dict[str, set[str]]:
    """モデルごとの relationship 属性名。"""
    source = MODELS_FILE.read_text()
    found = {}
    for block in re.split(r"\nclass ", source)[1:]:
        name = block.split("(")[0].strip()
        found[name] = set(re.findall(r"^    (\w+) = relationship\(", block, re.M))
    return found


def _response_fields(model) -> set[str]:
    """`response_model` のフィールド名。`list[X]` や入れ子の items も辿る。"""
    args = getattr(model, "__args__", None)
    if args:
        model = args[0]
    if not (inspect.isclass(model) and issubclass(model, BaseModel)):
        return set()

    fields = set(model.model_fields)
    for name, field in model.model_fields.items():
        if name != "items":
            continue
        inner = getattr(field.annotation, "__args__", None)
        if inner:
            fields |= _response_fields(inner[0])
    return fields


def _loads_eagerly(source: str) -> bool:
    """eager load しているか。呼び出し先のサービスまで1段だけ辿る。

    エンドポイントが `ApprovalWorkflowService.approve(...)` のように委譲して
    いる場合、eager load は呼び出し先にある。ここを見ないと誤検出になり、
    例外リストに登録して回ることになる（そして例外は古くなる）。
    """
    if any(marker in source for marker in _EAGER):
        return True

    for service_name, method in re.findall(r"\b([A-Z]\w*(?:Service|Draft))\.(\w+)\s*\(", source):
        target = _service_method_source(service_name, method)
        if target and any(marker in target for marker in _EAGER):
            return True
    return False


def _service_method_source(service_name: str, method: str) -> str | None:
    """`app/services` から該当メソッドのソースを探す。"""
    services = pathlib.Path(__file__).resolve().parents[1] / "app" / "services"
    pattern = re.compile(
        rf"^class {re.escape(service_name)}\b.*?(?=^class |\Z)", re.M | re.S
    )
    for path in services.rglob("*.py"):
        text = path.read_text()
        if f"class {service_name}" not in text:
            continue
        block = pattern.search(text)
        if not block:
            continue
        body = re.search(
            rf"^    (?:async )?def {re.escape(method)}\b.*?(?=^    (?:async )?def |\Z)",
            block.group(0),
            re.M | re.S,
        )
        if body:
            return body.group(0)
    return None


def _risky_routes() -> list[tuple[str, str, str, str]]:
    rels = _orm_relationships()
    risky = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.response_model is None:
            continue
        method = ",".join(sorted(route.methods))
        if (route.path, method) in ALLOWED:
            continue
        fields = _response_fields(route.response_model)
        if not fields:
            continue
        try:
            source = inspect.getsource(route.endpoint)
        except OSError:  # pragma: no cover -- 動的に定義された関数
            continue
        if _loads_eagerly(source):
            continue
        for orm, rel_names in rels.items():
            overlap = rel_names & fields
            if overlap and re.search(rf"\b{orm}\b", source):
                risky.append((method, route.path, route.endpoint.__name__, f"{orm}.{sorted(overlap)}"))
                break
    return risky


def test_routes_were_discovered():
    """検査対象が取れないまま「問題なし」になっていないこと。"""
    assert len([r for r in app.routes if isinstance(r, APIRoute) and r.response_model]) > 50


def test_no_response_model_lazy_loads_a_relationship():
    risky = _risky_routes()
    detail = "\n".join(f"  {m} {p} — {fn}() が {rel} を遅延ロード" for m, p, fn, rel in risky)
    assert not risky, (
        "応答に含めるリレーションを eager load していない（非同期セッションで500になる）:\n"
        f"{detail}\n"
        "selectinload / joinedload、または refresh(attribute_names=[...]) を使うこと。"
    )


@pytest.mark.parametrize("marker", [m for m in _EAGER if m != "attribute_names"])
def test_eager_markers_are_real_loader_options(marker):
    """判定に使う目印が実在する SQLAlchemy のローダ名であること。

    綴りを間違えると、eager load しているコードを見落として誤検出するか、
    逆に検出漏れになる。リポジトリでの使用有無ではなく、APIとして
    実在するかで確かめる（今は使っていない書き方も許容したいため）。
    """
    import sqlalchemy.orm

    assert hasattr(sqlalchemy.orm, marker), f"{marker} は SQLAlchemy のローダではない"
