"""テナントスコープの網羅チェック（静的走査）。

会社に紐づくテーブルを `company_id` で絞らず、かつ `scope_to_tenant` も通さずに
引いているエンドポイントが無いことを、ソースを解析して確認する。

個々のエンドポイントにテストを書く方式では、新しく追加された行に対しては
何も言えず、同じ越境が別のファイルで再発する。「未スコープの参照が0件」という
性質そのものを固定して、追加された行にも自動的に効くようにする。

意図的に例外を作る場合は ALLOWED に理由付きで登録すること。
"""
import ast
import pathlib

import pytest

ENDPOINTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "endpoints"

# company_id を持ち、テナント越境の対象になるモデル。
SCOPED_MODELS = {
    "Account",
    "AttendanceRecord",
    "Budget",
    "Employee",
    "FixedAsset",
    "JobExecution",
    "JournalHeader",
    "ScheduledJob",
    "TaxReturn",
}

# (ファイル名, モデル名) の意図的な例外。理由を必ず書く。
ALLOWED: dict[tuple[str, str], str] = {}


def _chain_source(source: str, node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    """`select(X)` からメソッドチェーンを辿った全体のソースを返す。

    `select(X).where(...).order_by(...)` のように連なっている場合、
    どこに company_id 条件が付いていても拾えるようにする。
    """
    top = node
    while True:
        parent = parents.get(top)
        if isinstance(parent, ast.Attribute) or (isinstance(parent, ast.Call) and parent.func is top):
            top = parent
        else:
            break
    return ast.get_source_segment(source, top) or ""


def _is_scoped(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """先祖に `scope_to_tenant(...)` の呼び出しがあるか。"""
    cur = parents.get(node)
    while cur is not None:
        if (
            isinstance(cur, ast.Call)
            and isinstance(cur.func, ast.Name)
            and cur.func.id == "scope_to_tenant"
        ):
            return True
        cur = parents.get(cur)
    return False


def _unscoped_selects(path: pathlib.Path) -> list[tuple[int, str]]:
    source = path.read_text()
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "select"):
            continue
        if len(node.args) != 1 or not isinstance(node.args[0], ast.Name):
            continue
        model = node.args[0].id
        if model not in SCOPED_MODELS:
            continue
        if (path.name, model) in ALLOWED:
            continue
        if _is_scoped(node, parents):
            continue
        if "company_id" in _chain_source(source, node, parents):
            continue
        found.append((node.lineno, model))
    return found


ENDPOINT_FILES = sorted(ENDPOINTS_DIR.glob("*.py"))


def test_endpoint_files_are_discovered():
    """走査対象が見つからないまま「全部OK」になっていないこと。"""
    assert len(ENDPOINT_FILES) > 10


@pytest.mark.parametrize("path", ENDPOINT_FILES, ids=lambda p: p.name)
def test_no_unscoped_tenant_lookup(path: pathlib.Path):
    unscoped = _unscoped_selects(path)
    detail = ", ".join(f"{path.name}:{ln} select({model})" for ln, model in unscoped)
    assert not unscoped, (
        f"テナントスコープの無い参照が残っている: {detail}. "
        "company_id で絞るか scope_to_tenant() を通すこと。"
    )


def test_scanner_detects_an_unscoped_lookup(tmp_path):
    """走査ロジック自体が機能していること（常に空を返す実装になっていないか）。"""
    sample = tmp_path / "sample.py"
    sample.write_text("from sqlalchemy import select\nx = select(FixedAsset).where(FixedAsset.asset_id == 1)\n")
    assert _unscoped_selects(sample) == [(2, "FixedAsset")]


def test_scanner_accepts_a_scoped_lookup(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from sqlalchemy import select\n"
        "x = scope_to_tenant(select(FixedAsset).where(FixedAsset.asset_id == 1), FixedAsset, t)\n"
    )
    assert _unscoped_selects(sample) == []


def test_scanner_accepts_an_explicit_company_filter(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from sqlalchemy import select\nx = select(Budget).where(Budget.company_id == cid)\n"
    )
    assert _unscoped_selects(sample) == []
