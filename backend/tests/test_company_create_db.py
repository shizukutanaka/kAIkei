"""会社の作成（登録直後の利用者が最初に通る経路）。

`POST /companies` が存在せず、会社を作る手段が**APIに一切無かった**。
ほぼ全ての機能が company_id を要求するため、登録した利用者はどの画面も
使えない状態だった。画面の空状態は「UUIDを入力」と表示しており、
入手する方法の無い値を求めていた。

テストが全てDBへ直接INSERTしていたため、この欠落は検出されていなかった。
実際にサーバを起動して登録から辿って初めて分かったので、HTTP経路で固定する。
"""
import uuid

import pytest
import pytest_asyncio

from app.models.models import Company, Tenant, User

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def api(api_client):
    return api_client


@pytest_asyncio.fixture
async def tenants(db_session):
    """管理者と、権限の無い利用者を持つ2テナント。"""
    from app.core.security import create_access_token

    made = {}
    for key, code, role in (("a", "CA", "admin"), ("b", "CB", "admin"), ("viewer", "CV", "viewer")):
        tenant = Tenant(tenant_name=f"T {code}", tenant_code=f"{code}-{uuid.uuid4().hex[:6]}")
        db_session.add(tenant)
        await db_session.flush()
        user = User(
            tenant_id=tenant.tenant_id,
            email=f"{code.lower()}-{uuid.uuid4().hex[:6]}@example.com",
            password_hash="x",
            display_name=f"U {code}",
            role=role,
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        made[key] = {
            "tenant_id": tenant.tenant_id,
            "token": create_access_token(str(user.user_id)),
        }
    return made


def _auth(entry):
    return {"Authorization": f"Bearer {entry['token']}"}


async def _create(api, entry, **overrides):
    body = {
        "company_name": "デモ商事",
        "company_code": f"C{uuid.uuid4().hex[:6]}",
        **overrides,
    }
    return await api.post("/api/v1/companies", json=body, headers=_auth(entry))


async def test_a_registered_user_can_create_a_company(api, tenants):
    """登録直後の利用者が会社を作れること（これが無いと何も使えない）。"""
    res = await _create(api, tenants["a"])

    assert res.status_code == 201, res.text
    assert res.json()["company_name"] == "デモ商事"


async def test_the_created_company_appears_in_the_list(api, tenants):
    created = (await _create(api, tenants["a"])).json()

    listed = await api.get("/api/v1/companies", headers=_auth(tenants["a"]))

    assert listed.status_code == 200
    assert created["company_id"] in [c["company_id"] for c in listed.json()]


async def test_the_company_belongs_to_the_callers_tenant(api, tenants, db_session):
    """テナントは認証情報から取ること。

    クライアントから受け取ると他テナントに会社を作れてしまい、
    テナント分離が根元から崩れる。
    """
    from sqlalchemy import select

    other = tenants["b"]["tenant_id"]
    created = (await _create(api, tenants["a"], tenant_id=str(other))).json()

    company = (
        await db_session.execute(
            select(Company).where(Company.company_id == uuid.UUID(created["company_id"]))
        )
    ).scalar_one()

    assert company.tenant_id == tenants["a"]["tenant_id"], "指定した tenant_id が通ってしまっている"
    assert company.tenant_id != other


async def test_another_tenant_does_not_see_it(api, tenants):
    """作成した会社が他テナントの一覧に出ないこと。"""
    created = (await _create(api, tenants["a"])).json()

    listed = await api.get("/api/v1/companies", headers=_auth(tenants["b"]))

    assert created["company_id"] not in [c["company_id"] for c in listed.json()]


async def test_duplicate_code_within_a_tenant_is_rejected(api, tenants):
    code = f"DUP{uuid.uuid4().hex[:6]}"
    first = await _create(api, tenants["a"], company_code=code)
    assert first.status_code == 201

    second = await _create(api, tenants["a"], company_code=code)

    assert second.status_code == 409


async def test_the_same_code_is_allowed_in_another_tenant(api, tenants):
    """会社コードの一意性はテナント内で足りる。"""
    code = f"SAME{uuid.uuid4().hex[:6]}"
    assert (await _create(api, tenants["a"], company_code=code)).status_code == 201

    assert (await _create(api, tenants["b"], company_code=code)).status_code == 201


async def test_permission_is_required(api, tenants):
    """master:create を持たない利用者は作成できないこと。"""
    res = await _create(api, tenants["viewer"])

    assert res.status_code == 403


async def test_unauthenticated_is_rejected(api):
    res = await api.post(
        "/api/v1/companies", json={"company_name": "x", "company_code": "y"}
    )

    assert res.status_code == 401


async def test_invalid_tax_method_is_rejected(api, tenants):
    res = await _create(api, tenants["a"], tax_method="not_a_method")

    assert res.status_code == 422


async def test_blank_name_is_rejected(api, tenants):
    res = await _create(api, tenants["a"], company_name="")

    assert res.status_code == 422
