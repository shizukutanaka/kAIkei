"""company_id を取る一覧系エンドポイントの疎通確認。

**データを1件も入れずに叩くと、行を処理するコードが実行されない。**
監査エクスポートは列名を間違えていたが、空の会社では取得が0件で
ループ本体に入らないため 200 を返し、この疎通確認を通り抜けていた。
実データを入れて初めて 500 になる。そのため会社には仕訳を1件入れておく。

テナント検証の依存関係 `verified_company_id` を91箇所に一括で入れたため、
どこか1つでも配線を間違えると、その画面だけ静かに壊れる。個別に気付くのは
難しいので、company_id だけで呼べる GET を機械的に列挙して全て叩く。

ここで見たいのは「自テナントの正しい company_id で 404 や 500 にならないこと」
だけで、レスポンスの中身は各機能のテストの担当。逆に、他テナントの company_id
では全て 404 になることも同じ一覧で確認する（1本でも検証漏れがあれば落ちる）。
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from app.main import app
from app.models.models import Company, Tenant, User

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


def _company_only_get_paths() -> list[str]:
    """company_id だけで呼べる GET エンドポイントを列挙する。

    ルーティングから引くので、エンドポイントが増えても自動的に対象になる。
    """
    paths = []
    for route in app.routes:
        if not hasattr(route, "dependant") or "GET" not in getattr(route, "methods", set()):
            continue
        deps = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
        if "verified_company_id" not in deps:
            continue
        if "{" in route.path_format:
            continue
        if any(p.required and p.name != "company_id" for p in route.dependant.query_params):
            continue
        paths.append(route.path)
    return sorted(paths)


SMOKE_PATHS = _company_only_get_paths()


@pytest_asyncio.fixture
async def api(api_client):
    """共有の `api_client`（conftest.py）を使う。

    ミドルウェアのセッション差し替えとレート制限の解除はそこに集約している。
    """
    return api_client


@pytest_asyncio.fixture
async def two_tenants(db_session):
    from app.core.security import create_access_token

    made = {}
    for key, code in (("a", "SA"), ("b", "SB")):
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
            password_hash="x",
            display_name=f"Admin {code}",
            role="admin",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        made[key] = {
            "company_id": company.company_id,
            "user_id": user.user_id,
            "token": create_access_token(str(user.user_id)),
        }

    # 空の会社だと行の処理が走らず、列名の誤りなどを見逃す。
    await _seed_a_journal(db_session, made["a"])
    return made


async def _seed_a_journal(db_session, entry) -> None:
    """疎通確認用に仕訳を1件入れる（借方・貸方1行ずつ）。"""
    from app.models.models import Account, JournalHeader, JournalLine

    cash = Account(
        company_id=entry["company_id"],
        account_code="1000",
        account_name="現金",
        account_type="asset",
        debit_credit="debit",
    )
    sales = Account(
        company_id=entry["company_id"],
        account_code="4000",
        account_name="売上",
        account_type="revenue",
        debit_credit="credit",
    )
    db_session.add_all([cash, sales])
    await db_session.flush()

    header = JournalHeader(
        company_id=entry["company_id"],
        journal_number=f"J-{uuid4().hex[:8]}",
        transaction_date=date(2026, 6, 15),
        summary="疎通確認",
        approval_status="approved",
        created_by=entry["user_id"],
    )
    db_session.add(header)
    await db_session.flush()

    db_session.add_all(
        [
            JournalLine(
                journal_header_id=header.journal_header_id,
                line_number=1,
                debit_credit="debit",
                account_id=cash.account_id,
                amount=Decimal("110000"),
            ),
            JournalLine(
                journal_header_id=header.journal_header_id,
                line_number=2,
                debit_credit="credit",
                account_id=sales.account_id,
                amount=Decimal("110000"),
            ),
        ]
    )
    await db_session.flush()


def test_smoke_paths_were_discovered():
    """列挙に失敗したまま「全部OK」になっていないこと。"""
    assert len(SMOKE_PATHS) > 15


@pytest.mark.parametrize("path", SMOKE_PATHS)
async def test_own_company_is_not_rejected(api, two_tenants, path):
    a = two_tenants["a"]
    res = await api.get(
        path,
        params={"company_id": str(a["company_id"])},
        headers={"Authorization": f"Bearer {a['token']}"},
    )

    assert res.status_code != 404, f"{path}: 自テナントの company_id が弾かれている"
    assert res.status_code < 500, f"{path}: サーバエラー {res.status_code} / {res.text[:300]}"


@pytest.mark.parametrize("path", SMOKE_PATHS)
async def test_other_tenants_company_is_rejected(api, two_tenants, path):
    a, b = two_tenants["a"], two_tenants["b"]
    res = await api.get(
        path,
        params={"company_id": str(b["company_id"])},
        headers={"Authorization": f"Bearer {a['token']}"},
    )

    assert res.status_code == 404, f"{path}: 他テナントの company_id が通っている ({res.status_code})"
