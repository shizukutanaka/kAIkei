"""UUID を受け取る経路がテナントを照合していることの検証（静的走査）。

`company_id` をクエリで受け取る経路は依存関係 `verified_company_id` で
一律に照合していた。しかし**エンティティのIDを受け取る**経路には
その仕組みが無く、各エンドポイントの書き方に委ねられていた。結果として、

- `/approvals` の5経路（承認・記帳・差戻・提出・履歴）
- `/journals/{id}/approve`、`/journals/{id}/post`
- 賞与明細・給与明細・年末調整・経費精算・請求書の各エクスポート
- `/masters/sub-accounts/by-account/{account_id}`

が、UUID を知っているだけで他テナントから操作・閲覧できる状態だった。
承認と記帳は読み取りではなく**書き込み**で、他社の帳簿が第三者の操作で
確定していた。

個別にテストを足す方式では、次に追加されるエンドポイントには何も言えない。
「UUIDを受け取るのに照合していない経路が0件」という性質を固定する。

**この走査の限界**: 判定は「その関数のどこかに照合の目印があるか」であって、
「受け取る全てのIDが照合されているか」ではない。実際、勤怠打刻は
`company_id` を `assert_company_access` で照合していたためここを通過したが、
`employee_id` は照合しておらず、他テナントの従業員で自社の勤怠を作れた
（存在しないIDなら外部キー違反で500）。**IDごとの追跡はここでは行わない。**
その種類は `test_write_endpoint_smoke_db.py` が実際に叩いて見つける。
片方だけでは足りないので、両方を維持すること。
"""
import inspect
from uuid import UUID

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.main import app

# 照合していると判断する目印。
_GUARDS = (
    "assert_owns",
    "scope_to_tenant",
    "assert_company_access",
    "verified_company_id",
    "tenant_id",
    "tenant_company_ids",
)

# 意図的な例外。(パス, メソッド) -> 理由。
ALLOWED: dict[tuple[str, str], str] = {}


def _entity_ids(route: APIRoute) -> list[str]:
    """パスとリクエストボディで受け取る UUID の名前。

    `company_id` は `verified_company_id` 側の担当なので数えない。
    """
    found = [p.name for p in route.dependant.path_params if p.type_ is UUID]
    for param in route.dependant.body_params:
        model = param.type_
        if inspect.isclass(model) and issubclass(model, BaseModel):
            found += [
                name
                for name, field in model.model_fields.items()
                if field.annotation is UUID and name != "company_id"
            ]
    return found


def _unscoped_routes() -> list[tuple[str, str, str, list[str]]]:
    risky = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        method = ",".join(sorted(route.methods - {"HEAD", "OPTIONS"}))
        if (route.path, method) in ALLOWED:
            continue
        ids = _entity_ids(route)
        if not ids:
            continue
        try:
            source = inspect.getsource(route.endpoint)
        except OSError:  # pragma: no cover -- 動的に定義された関数
            continue
        deps = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
        if any(g in source for g in _GUARDS) or "verified_company_id" in deps:
            continue
        risky.append((method, route.path, route.endpoint.__name__, ids))
    return sorted(risky, key=lambda r: r[1])


def test_id_taking_routes_were_discovered():
    """走査に失敗したまま「問題なし」になっていないこと。"""
    taking_ids = [
        r for r in app.routes if isinstance(r, APIRoute) and _entity_ids(r)
    ]
    assert len(taking_ids) > 40, f"UUIDを受け取る経路が {len(taking_ids)} 本しか見つからない"


def test_no_id_route_skips_the_tenant_check():
    risky = _unscoped_routes()
    detail = "\n".join(f"  {m} {p} — {fn}() が {ids} を照合していない" for m, p, fn, ids in risky)
    assert not risky, (
        "UUID を受け取るのにテナントを照合していない経路がある"
        "（IDを知っているだけで他テナントのデータを操作・閲覧できる）:\n"
        f"{detail}\n"
        "assert_owns() か scope_to_tenant() を、状態チェックより前に通すこと。"
    )


@pytest.mark.parametrize("guard", ["assert_owns", "scope_to_tenant", "assert_company_access"])
def test_the_guards_actually_exist(guard):
    """目印にしている関数名が実在すること。

    綴りを間違えると、照合していない経路を「照合済み」と誤判定する。
    """
    import app.core.tenant_scope as scope

    assert hasattr(scope, guard), f"{guard} は tenant_scope に存在しない"
