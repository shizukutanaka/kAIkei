"""テナント越境をHTTP経路で確認する統合テスト。

`test_tenant_scope_db.py` がクエリ条件そのものを検証するのに対し、こちらは
「実際にリクエストを投げたら他社のデータが返らないか」を確認する。
依存関係の配線ミス（`verified_company_id` を付け忘れた、順序の都合で
権限チェックより後になった等）はクエリ単体のテストでは検出できない。
"""
from uuid import uuid4

import pytest
import pytest_asyncio

from app.core.passwords import hash_password
from app.models.models import Budget, Company, Tenant, User

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def api(api_client):
    """共有の `api_client`（conftest.py）を使う。

    ミドルウェアのセッション差し替えとレート制限の解除はそこに集約している。
    """
    return api_client


@pytest_asyncio.fixture
async def tenants(db_session):
    """2テナント（会社1社・管理者1名ずつ）と、それぞれの予算を用意する。"""
    from app.core.security import create_access_token

    made = {}
    for key, code in (("a", "TA"), ("b", "TB")):
        tenant = Tenant(tenant_name=f"Tenant {code}", tenant_code=f"{code}-{uuid4().hex[:6]}")
        db_session.add(tenant)
        await db_session.flush()

        company = Company(
            tenant_id=tenant.tenant_id,
            company_name=f"Co {code}",
            company_code=f"{code}-{uuid4().hex[:6]}",
        )
        db_session.add(company)
        await db_session.flush()

        user = User(
            tenant_id=tenant.tenant_id,
            email=f"{code.lower()}-{uuid4().hex[:6]}@example.com",
            password_hash=hash_password("password-for-test"),
            display_name=f"Admin {code}",
            role="admin",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        budget = Budget(
            company_id=company.company_id,
            fiscal_year=2026,
            name=f"{code} の予算",
            status="draft",
        )
        db_session.add(budget)
        await db_session.flush()

        made[key] = {
            "company_id": company.company_id,
            "budget_id": budget.budget_id,
            "token": create_access_token(str(user.user_id)),
        }
    return made


def _auth(entry) -> dict[str, str]:
    return {"Authorization": f"Bearer {entry['token']}"}


async def test_own_company_budgets_are_visible(api, tenants):
    """自社の予算は今まで通り見えること（防御でデータを潰していない）。"""
    a = tenants["a"]
    res = await api.get("/api/v1/budgets", params={"company_id": str(a["company_id"])}, headers=_auth(a))

    assert res.status_code == 200
    assert [b["name"] for b in res.json()] == ["TA の予算"]


async def test_other_tenants_company_id_is_rejected(api, tenants):
    """他テナントの company_id を渡しても、その会社のデータは返らない。"""
    a, b = tenants["a"], tenants["b"]
    res = await api.get("/api/v1/budgets", params={"company_id": str(b["company_id"])}, headers=_auth(a))

    assert res.status_code == 404, res.text
    assert "TB の予算" not in res.text


async def test_unknown_company_id_is_rejected(api, tenants):
    """存在しない company_id も同じく 404（存在有無を出し分けない）。"""
    a = tenants["a"]
    res = await api.get("/api/v1/budgets", params={"company_id": str(uuid4())}, headers=_auth(a))

    assert res.status_code == 404


async def test_other_tenants_budget_id_is_not_readable(api, tenants):
    """ID直指定でも他テナントの予算は取得できない。"""
    a, b = tenants["a"], tenants["b"]
    res = await api.get(f"/api/v1/budgets/{b['budget_id']}", headers=_auth(a))

    assert res.status_code == 404, res.text


async def test_own_budget_id_is_readable(api, tenants):
    a = tenants["a"]
    res = await api.get(f"/api/v1/budgets/{a['budget_id']}", headers=_auth(a))

    assert res.status_code == 200
    assert res.json()["name"] == "TA の予算"


async def test_cannot_create_into_another_tenants_company(api, tenants):
    """リクエストボディで他テナントの company_id を指定しても作成できない。

    参照系より重い。防げないと他社の帳簿に行を書き込めることになる。
    """
    a, b = tenants["a"], tenants["b"]
    res = await api.post(
        "/api/v1/budgets",
        json={
            "company_id": str(b["company_id"]),
            "fiscal_year": 2027,
            "name": "他社に作った予算",
            "lines": [],
        },
        headers=_auth(a),
    )

    assert res.status_code == 404, res.text

    # 実際に書き込まれていないことまで確認する。
    check = await api.get(
        "/api/v1/budgets", params={"company_id": str(b["company_id"])}, headers=_auth(b)
    )
    assert "他社に作った予算" not in check.text


async def test_can_create_into_own_company(api, tenants):
    """自社への作成は従来通り通ること。"""
    a = tenants["a"]
    res = await api.post(
        "/api/v1/budgets",
        json={
            "company_id": str(a["company_id"]),
            "fiscal_year": 2027,
            "name": "自社の予算",
            "lines": [],
        },
        headers=_auth(a),
    )

    assert res.status_code == 201, res.text
    assert res.json()["name"] == "自社の予算"


async def test_unauthenticated_request_is_rejected(api, tenants):
    """検証依存を足したことで認証が素通りしていないこと。"""
    a = tenants["a"]
    res = await api.get("/api/v1/budgets", params={"company_id": str(a["company_id"])})

    assert res.status_code == 401


async def test_request_is_recorded_in_the_audit_log(api, tenants, db_session):
    """実リクエストが監査ログに残ること（テナント・会社つきで）。

    旧実装は tenant_id に固定のゼロUUIDを入れており、外部キー違反で1件も
    残っていなかった。例外は握り潰されるため、行数で確認する。
    """
    from sqlalchemy import func, select

    from app.models.models import AuditLog

    a = tenants["a"]
    before = (await db_session.execute(select(func.count()).select_from(AuditLog))).scalar_one()

    res = await api.post(
        "/api/v1/budgets",
        json={
            "company_id": str(a["company_id"]),
            "fiscal_year": 2028,
            "name": "証跡確認用",
            "lines": [],
        },
        headers=_auth(a),
    )
    assert res.status_code == 201, res.text

    rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.path == "/api/v1/budgets").order_by(AuditLog.created_at.desc())
        )
    ).scalars().all()
    after = (await db_session.execute(select(func.count()).select_from(AuditLog))).scalar_one()

    assert after == before + 1, "監査ログが書き込まれていない"
    log = rows[0]
    assert log.tenant_id is not None, "tenant_id が解決されていない"
    assert log.company_id == a["company_id"], "company_id が記録されていない（会社別の証跡一覧が空になる）"
    assert log.method == "POST"
    assert log.status_code == 201
