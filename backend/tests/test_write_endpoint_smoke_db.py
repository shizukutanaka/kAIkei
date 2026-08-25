"""POST / PUT / PATCH / DELETE の疎通確認。

GET 128本は疎通確認するようになったが、**非GETの140本は一度も叩いていない**。
実際に見つかった最悪の欠陥（他テナントの仕訳を承認・記帳できた、賞与計算が
呼べば必ず500）はどちらも書き込み側にあった。読み取りだけ確認しても足りない。

リクエスト本文は**スキーマから機械的に生成する**。必須フィールドを型に応じて
埋めるだけなので業務的に妥当な値にはならないが、ここで見たいのは
「サーバエラーにならないこと」だけ。値がおかしければ 400/422 が返るはずで、
それは正常な応答として扱う。500 が返るなら、値ではなくコードの問題。

DB を書き換えるが、各テストはセーブポイントで巻き戻るので後には残らない。
"""
import datetime
import enum
import inspect
import typing
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import UploadFile
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.main import app
from app.models.models import Company, Tenant, User
from tests.test_endpoint_smoke_db import _seed_a_journal
from tests.test_endpoint_smoke_wide_db import _value_for

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

# 意図的に叩かないもの。理由を必ず書く（黙って外さない）。
EXCLUDED: dict[str, str] = {
    "/api/v1/knowledge/ai-context": "外部サイトへ実際に取得しに行く",
    "/api/v1/knowledge/search": "外部サイトへ実際に取得しに行く",
    "/api/v1/webhooks/process": "登録先へ実際に送信しに行く",
    "/api/v1/integrations/import": "外部会計ソフトへ接続しに行く",
}

# 外部の推論エンジンへ接続しに行く配下。
EXCLUDED_PREFIXES: dict[str, str] = {
    "/api/v1/ai/": "AIプロバイダへ実際に問い合わせる",
}

_COMPANY = "{company_id}"


def _generate(annotation, name: str = "", depth: int = 0):
    """型注釈から値を1つ作る。作れなければ `_Unfillable` を返す。"""
    if depth > 4:
        return _Unfillable

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # Optional[X] / X | None は必須フィールドでも None を許すので None でよい
    if origin is typing.Union or str(origin) == "<class 'types.UnionType'>":
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) < len(args):
            return None
        return _generate(non_none[0], name, depth + 1)

    if origin is typing.Literal:
        return args[0]
    if origin in (list, set, tuple):
        inner = _generate(args[0], name, depth + 1) if args else _Unfillable
        return _Unfillable if inner is _Unfillable else [inner]
    if origin is dict:
        return {}

    if annotation is dict:
        return {}
    if annotation is list:
        return []

    if inspect.isclass(annotation):
        if issubclass(annotation, enum.Enum):
            return next(iter(annotation)).value
        if issubclass(annotation, BaseModel):
            return _generate_body(annotation, depth + 1)
        if annotation is UUID:
            return _COMPANY if name == "company_id" else str(uuid4())
        if annotation is datetime.datetime:
            return "2026-06-15T00:00:00"
        if annotation is bool:
            return False

    scalar = _value_for(name or "value", annotation)
    if scalar is not None:
        if annotation is int:
            return int(scalar)
        if annotation in (Decimal, float):
            return scalar if annotation is Decimal else float(scalar)
        return scalar
    return _Unfillable


class _Unfillable:
    """値を作れなかったことを表す番兵。None と区別するために使う。"""


def _generate_body(model: type[BaseModel], depth: int = 0) -> dict:
    body = {}
    for name, field in model.model_fields.items():
        if not field.is_required():
            continue
        value = _generate(field.annotation, name, depth)
        if value is _Unfillable:
            return _Unfillable
        body[name] = value
    return body


def _plan_requests() -> tuple[list, list]:
    ready, unfillable = [], []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = route.methods - {"GET", "HEAD", "OPTIONS"}
        if not methods:
            continue
        if route.path in EXCLUDED or any(
            route.path.startswith(p) for p in EXCLUDED_PREFIXES
        ):
            continue

        missing = []
        body = None
        upload = None
        if route.dependant.body_params:
            param = route.dependant.body_params[0]
            model = param.type_
            if inspect.isclass(model) and issubclass(model, UploadFile):
                # ファイル取り込みは中身が空だと解析に入らないので、
                # ヘッダー付きの最小のCSVを送る。
                upload = param.name
            elif inspect.isclass(model) and issubclass(model, BaseModel):
                body = _generate_body(model)
                if body is _Unfillable:
                    missing.append(f"body: {model.__name__}")
            else:
                built = _generate(model, param.name)
                if built is _Unfillable:
                    missing.append(f"body: {model}")
                else:
                    body = {param.name: built}

        params = {}
        for param in route.dependant.query_params:
            if not param.required:
                continue
            value = (
                _COMPANY if param.name == "company_id" else _value_for(param.name, param.type_)
            )
            if value is None:
                missing.append(f"{param.name}: {param.type_}")
            else:
                params[param.name] = value

        path = route.path
        for param in route.dependant.path_params:
            value = _value_for(param.name, param.type_)
            if value is None:
                missing.append(f"{param.name}: {param.type_}")
            else:
                path = path.replace("{" + param.name + "}", value)

        method = sorted(methods)[0]
        if missing:
            unfillable.append((f"{method} {route.path}", missing))
            continue
        ready.append(
            pytest.param(method, path, params, body, upload, id=f"{method} {route.path}")
        )

    return ready, unfillable


REQUESTS, UNFILLABLE = _plan_requests()


@pytest_asyncio.fixture
async def api(api_client):
    return api_client


@pytest_asyncio.fixture
async def company(db_session):
    from app.core.security import create_access_token

    tenant = Tenant(tenant_name="WR", tenant_code=f"WR-{uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    co = Company(
        tenant_id=tenant.tenant_id,
        company_name="書込商事",
        company_code=f"WR-{uuid4().hex[:6]}",
    )
    db_session.add(co)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"wr-{uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="書込",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    entry = {"company_id": co.company_id, "user_id": user.user_id}
    await _seed_a_journal(db_session, entry)
    entry["token"] = create_access_token(str(user.user_id))
    return entry


def _resolve(value, company_id):
    """生成時に置いた `{company_id}` を実際の値に差し替える。"""
    if value == _COMPANY:
        return str(company_id)
    if isinstance(value, dict):
        return {k: _resolve(v, company_id) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, company_id) for v in value]
    return value


def test_every_write_route_is_either_covered_or_excluded():
    """確認対象から漏れた書き込み経路が無いこと。"""
    detail = "\n".join(f"  {route} — {missing}" for route, missing in UNFILLABLE)
    assert not UNFILLABLE, f"本文を生成できない書き込み経路が残っている:\n{detail}"


def test_the_plan_is_not_empty():
    """列挙に失敗したまま「全部OK」になっていないこと。"""
    assert len(REQUESTS) > 110, f"叩く対象が {len(REQUESTS)} 本しかない"


# 取り込み経路に送る最小のCSV。中身が空だと解析ループに入らず、
# 行を処理するコードの欠陥を見逃す（監査エクスポートがまさにそれだった）。
_CSV = "取引日,借方勘目,貸方勘目,摘要,金額\n2026-06-15,現金,売上,疎通確認,110000\n"


@pytest.mark.parametrize("method,path,params,body,upload", REQUESTS)
async def test_the_endpoint_does_not_fail(api, company, method, path, params, body, upload):
    """サーバエラーにならないこと。400/403/404/409/422 は正常な応答として扱う。"""
    cid = company["company_id"]
    files = (
        {upload: ("smoke.csv", _CSV.encode("utf-8"), "text/csv")} if upload else None
    )
    res = await api.request(
        method,
        path,
        params=_resolve(params, cid),
        json=_resolve(body, cid) if body is not None else None,
        files=files,
        headers={"Authorization": f"Bearer {company['token']}"},
    )

    assert res.status_code < 500, (
        f"{method} {path} params={_resolve(params, cid)} body={_resolve(body, cid)}\n"
        f"  → {res.status_code} / {res.text[:400]}"
    )
