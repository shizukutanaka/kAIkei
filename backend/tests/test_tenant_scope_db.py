"""テナント越境アクセス（IDOR）に対する防御の検証。

このシステムは Tenant > Company > 業務データ という階層で、業務データは
company_id しか持たない。一方 JWT が運ぶのは tenant_id なので、
「この company は本当に自分のテナントのものか」を毎回照合しないと、
UUID を知っているだけで他社の仕訳・固定資産・決算書を読み書きできてしまう。

会計データの越境は単なる情報漏えいではなく、他社の帳簿を改竄できる
（例: 他テナントの仕訳を取消す）という意味を持つため、ここを共通の
スコープ条件として一箇所に固定する。
"""
import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.tenant_scope import scope_to_tenant, tenant_company_ids
from app.models.models import Company, FixedAsset, JournalHeader, Tenant, User

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def two_tenants(db_session):
    """独立した2テナント（それぞれ会社を1社持つ）を作る。"""
    made = {}
    for key, code in (("a", "TA"), ("b", "TB")):
        tenant = Tenant(tenant_name=f"Tenant {code}", tenant_code=code)
        db_session.add(tenant)
        await db_session.flush()
        company = Company(tenant_id=tenant.tenant_id, company_name=f"Co {code}", company_code=code)
        db_session.add(company)
        await db_session.flush()
        user = User(
            tenant_id=tenant.tenant_id,
            email=f"{code.lower()}@example.com",
            password_hash="x",
            display_name=f"User {code}",
            role="accountant",
        )
        db_session.add(user)
        await db_session.flush()
        made[key] = {
            "tenant_id": tenant.tenant_id,
            "company_id": company.company_id,
            "user_id": user.user_id,
        }
    return made


async def _add_asset(db_session, company_id) -> uuid.UUID:
    asset = FixedAsset(
        company_id=company_id,
        asset_code=f"FA-{uuid.uuid4().hex[:8]}",
        asset_name="社用車",
        asset_category="車両運搬具",
        acquisition_date=date(2026, 4, 1),
        acquisition_cost=3_000_000,
        salvage_value=0,
        useful_life_months=72,
        depreciation_method="straight_line",
        accumulated_depreciation=0,
    )
    db_session.add(asset)
    await db_session.flush()
    return asset.asset_id


async def test_tenant_company_ids_only_returns_own_companies(db_session, two_tenants):
    a, b = two_tenants["a"], two_tenants["b"]

    rows = (await db_session.execute(tenant_company_ids(a["tenant_id"]))).scalars().all()

    assert a["company_id"] in rows
    assert b["company_id"] not in rows


async def test_scoped_lookup_hides_other_tenants_asset(db_session, two_tenants):
    """他テナントの固定資産は、asset_id を知っていても取得できない。"""
    a, b = two_tenants["a"], two_tenants["b"]
    asset_id = await _add_asset(db_session, b["company_id"])

    # スコープ無し（従来の実装）だと見えてしまうことを、対比として示す。
    unscoped = await db_session.execute(select(FixedAsset).where(FixedAsset.asset_id == asset_id))
    assert unscoped.scalar_one_or_none() is not None

    scoped = await db_session.execute(
        scope_to_tenant(select(FixedAsset).where(FixedAsset.asset_id == asset_id), FixedAsset, a["tenant_id"])
    )
    assert scoped.scalar_one_or_none() is None


async def test_scoped_lookup_still_returns_own_asset(db_session, two_tenants):
    """自テナントのデータまで巻き添えで消さないこと。"""
    a = two_tenants["a"]
    asset_id = await _add_asset(db_session, a["company_id"])

    scoped = await db_session.execute(
        scope_to_tenant(select(FixedAsset).where(FixedAsset.asset_id == asset_id), FixedAsset, a["tenant_id"])
    )
    assert scoped.scalar_one_or_none() is not None


async def test_scoped_lookup_hides_other_tenants_journal(db_session, two_tenants):
    """仕訳の越境は「他社の帳簿を取消せる」を意味するため個別に固定する。"""
    a, b = two_tenants["a"], two_tenants["b"]
    header = JournalHeader(
        company_id=b["company_id"],
        transaction_date=date(2026, 4, 1),
        journal_number=f"J-{uuid.uuid4().hex[:8]}",
        summary="他社の仕訳",
        created_by=b["user_id"],
    )
    db_session.add(header)
    await db_session.flush()

    scoped = await db_session.execute(
        scope_to_tenant(
            select(JournalHeader).where(JournalHeader.journal_header_id == header.journal_header_id),
            JournalHeader,
            a["tenant_id"],
        )
    )
    assert scoped.scalar_one_or_none() is None


async def test_deleted_company_is_not_in_scope(db_session, two_tenants):
    """論理削除された会社のデータは、自テナントであってもスコープ外にする。"""
    a = two_tenants["a"]
    asset_id = await _add_asset(db_session, a["company_id"])

    company = (
        await db_session.execute(select(Company).where(Company.company_id == a["company_id"]))
    ).scalar_one()
    company.is_deleted = True
    await db_session.flush()

    scoped = await db_session.execute(
        scope_to_tenant(select(FixedAsset).where(FixedAsset.asset_id == asset_id), FixedAsset, a["tenant_id"])
    )
    assert scoped.scalar_one_or_none() is None
