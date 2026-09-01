"""残る全ての GET エンドポイントの疎通確認。

`test_endpoint_smoke_db.py` は「company_id だけで呼べる GET」に限っていた。
それは 128 本ある GET のうち **28 本**でしかない。残り 100 本は、必須の
クエリパラメータがある（`as_of`、`year`、`taxable_income` …）か、パスに
ID を含む（`/budgets/{budget_id}` …）という理由だけで対象外になっていた。

「対象外」は「確認済み」ではない。実際、監査エクスポートは列名を2回続けて
間違えていて、いずれも起動して叩くまで気付けなかった。同じ壊れ方
（存在しない属性、遅延ロード、SQLの綴り誤り）は残り100本のどこにでも
あり得るし、あっても誰も気付かない。

そこでパラメータを**型と名前から機械的に埋めて**全部叩く。見たいのは
「サーバエラーにならないこと」だけ。値が業務的に妥当かは各機能のテストの
担当で、ここでは 400/403/422 は正常な応答として扱う。

パスIDには存在しない UUID を渡す。これで「照会そのものが実行される」
（SQLが組み立てられ、列が実在し、テナント絞り込みが走る）ことを確認でき、
かつ他人のIDを推測されても 404 になることも同時に固定できる。
"""
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute

from app.main import app
from app.models.models import Company, Tenant, User
from tests.test_endpoint_smoke_db import SMOKE_PATHS, _seed_a_journal

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

# 意図的に叩かないもの。理由を必ず書く（黙って外さない）。
EXCLUDED: dict[str, str] = {
    "/api/v1/knowledge/search": "外部サイトへ実際に取得しに行く",
    "/api/v1/knowledge/detail/{source_code}": "外部サイトへ実際に取得しに行く",
    # テスト用DB（TEST_DATABASE_URL）ではなく設定上の接続先を見に行くので、
    # 稼働環境の状態を報告しているだけ。ここで見たいアプリの不具合ではない。
    "/health": "設定された接続先の死活を見るもので、テスト用DBとは別",
    "/api/v1/health": "同上（画面用の別名。ルート直下はロードバランサ用）",
}

# 列挙型に近い文字列パラメータ。外れても 422 で返るので厳密でなくてよい。
_STRINGS = {
    "business_type": "corporation",
    "business_category": "1",
    "bonus_term": "summer",
    "industry": "retail",
    "document_type": "invoice",
    "period": "monthly",
    "number": "T1234567890123",
    "topic": "japanese_tax",
    "permission": "journal:read",
}


def _value_for(name: str, annotation) -> str | None:
    """パラメータ名と型から、通してみる値を決める。決められなければ None。"""
    lowered = name.lower()

    if annotation is date:
        if "start" in lowered or "from" in lowered:
            return "2026-01-01"
        if "end" in lowered or "as_of" in lowered or lowered.endswith("_to"):
            return "2026-12-31"
        return "2026-06-15"
    if annotation in (Decimal, float):
        if "rate" in lowered:
            return "0.1"
        return "1000000"
    if annotation is int:
        if "months_of" in lowered:
            return "24"
        if "year" in lowered:
            return "2026"
        if "month" in lowered:
            return "6"
        if "day" in lowered:
            return "20"
        return "1"
    if annotation is bool:
        return "false"
    if annotation is UUID:
        return str(uuid4())
    if annotation is str:
        return _STRINGS.get(name, "1")
    return None


def _plan_requests() -> tuple[list, list]:
    """叩く GET を組み立てる。埋められなかったものは別に返す（黙って捨てない）。

    Returns:
        (叩けるもの, 埋められなかったもの)
    """
    ready, unfillable = [], []
    covered = set(SMOKE_PATHS)

    for route in app.routes:
        if not isinstance(route, APIRoute) or "GET" not in route.methods:
            continue
        if route.path in covered or route.path in EXCLUDED:
            continue

        params: dict[str, str] = {}
        missing = []
        for param in route.dependant.query_params:
            if not param.required:
                continue
            value = "{company_id}" if param.name == "company_id" else _value_for(
                param.name, param.type_
            )
            if value is None:
                missing.append(f"{param.name}: {param.type_}")
                continue
            params[param.name] = value

        path = route.path
        has_uuid_id = False
        for param in route.dependant.path_params:
            value = _value_for(param.name, param.type_)
            if value is None:
                missing.append(f"{param.name}: {param.type_}")
                continue
            has_uuid_id = has_uuid_id or param.type_ is UUID
            path = path.replace("{" + param.name + "}", value)

        if missing:
            unfillable.append((route.path, missing))
            continue
        ready.append(pytest.param(path, params, has_uuid_id, id=f"{route.path}"))

    return ready, unfillable


REQUESTS, UNFILLABLE = _plan_requests()


@pytest_asyncio.fixture
async def api(api_client):
    return api_client


@pytest_asyncio.fixture
async def company(db_session):
    """仕訳を1件持った会社。空だと行を処理するコードが実行されない。"""
    from app.core.security import create_access_token

    tenant = Tenant(tenant_name="WS", tenant_code=f"WS-{uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    co = Company(
        tenant_id=tenant.tenant_id,
        company_name="疎通商事",
        company_code=f"WS-{uuid4().hex[:6]}",
    )
    db_session.add(co)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"ws-{uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="疎通",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    entry = {"company_id": co.company_id, "user_id": user.user_id}
    await _seed_a_journal(db_session, entry)
    entry["token"] = create_access_token(str(user.user_id))
    return entry


def test_every_get_route_is_either_covered_or_excluded():
    """確認対象から漏れた GET が無いこと。

    埋められないパラメータが増えたら、値の決め方を足すか EXCLUDED に
    理由付きで載せる。放っておくと「対象外」が静かに増えていく。
    """
    detail = "\n".join(f"  {path} — {missing}" for path, missing in UNFILLABLE)
    assert not UNFILLABLE, f"パラメータを埋められない GET が残っている:\n{detail}"


def test_the_plan_is_not_empty():
    """列挙に失敗したまま「全部OK」になっていないこと。"""
    assert len(REQUESTS) > 80, f"叩く対象が {len(REQUESTS)} 本しかない"


@pytest.mark.parametrize("path,params,has_uuid_id", REQUESTS)
async def test_the_endpoint_does_not_fail(api, company, path, params, has_uuid_id):
    """サーバエラーにならないこと。400/403/422 は正常な応答として扱う。"""
    filled = {
        k: (str(company["company_id"]) if v == "{company_id}" else v) for k, v in params.items()
    }

    res = await api.get(
        path, params=filled, headers={"Authorization": f"Bearer {company['token']}"}
    )

    assert res.status_code < 500, f"{path} {filled} → {res.status_code} / {res.text[:400]}"


@pytest.mark.parametrize(
    "path,params,has_uuid_id", [r for r in REQUESTS if r.values[2]]
)
async def test_a_made_up_id_is_not_found(api, company, path, params, has_uuid_id):
    """存在しない UUID を渡したら 404 になること。

    照会が実際に実行されることの確認でもある（列名を間違えていれば
    ここで 500 になる）。200 が返るならIDを見ずに何かを返している。
    """
    filled = {
        k: (str(company["company_id"]) if v == "{company_id}" else v) for k, v in params.items()
    }

    res = await api.get(
        path, params=filled, headers={"Authorization": f"Bearer {company['token']}"}
    )

    assert res.status_code != 200, f"{path}: 存在しないIDで中身が返っている"
    assert res.status_code in (400, 403, 404, 422), f"{path} → {res.status_code} / {res.text[:300]}"
