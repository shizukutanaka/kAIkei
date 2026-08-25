"""パスにIDを取るエンドポイントのテナント分離。

テナント分離の確認は `company_id` をクエリで取るエンドポイントに限られていた。
`/approvals/history/{journal_header_id}` のように**IDをパスで受け取る**経路は
一度も確認されていない。存在しないUUIDを渡せば当然0件で返るので、
他人の実在するIDを渡してみないと漏れているかどうか分からない。

承認履歴は「誰がいつ何を承認し、どうコメントしたか」で、他社に見せてよい
情報ではない。
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.models import (
    Account,
    ApprovalLog,
    Company,
    JournalHeader,
    JournalLine,
    SubAccount,
    Tenant,
    User,
)

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def api(api_client):
    return api_client


async def _make_tenant(db_session, code: str):
    from app.core.security import create_access_token

    tenant = Tenant(tenant_name=f"T{code}", tenant_code=f"{code}-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    company = Company(
        tenant_id=tenant.tenant_id,
        company_name=f"Co{code}",
        company_code=f"{code}-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(company)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"{code.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name=code,
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return {
        "tenant_id": tenant.tenant_id,
        "company_id": company.company_id,
        "user_id": user.user_id,
        "token": create_access_token(str(user.user_id)),
    }


@pytest_asyncio.fixture
async def two_tenants(db_session):
    """A と B。B 側には承認済みの仕訳と補助科目を実際に作る。"""
    a = await _make_tenant(db_session, "PA")
    b = await _make_tenant(db_session, "PB")

    account = Account(
        company_id=b["company_id"],
        account_code="1000",
        account_name="現金",
        account_type="asset",
        debit_credit="debit",
    )
    db_session.add(account)
    await db_session.flush()
    db_session.add(
        SubAccount(
            account_id=account.account_id,
            sub_account_code="001",
            sub_account_name="B社の秘密の補助科目",
            is_active=True,
        )
    )

    header = JournalHeader(
        company_id=b["company_id"],
        journal_number=f"B-{uuid.uuid4().hex[:8]}",
        transaction_date=date(2026, 6, 15),
        summary="B社の取引",
        approval_status="approved",
        created_by=b["user_id"],
    )
    db_session.add(header)
    await db_session.flush()
    db_session.add(
        JournalLine(
            journal_header_id=header.journal_header_id,
            line_number=1,
            debit_credit="debit",
            account_id=account.account_id,
            amount=Decimal("110000"),
        )
    )
    db_session.add(
        ApprovalLog(
            journal_header_id=header.journal_header_id,
            action="approve",
            from_status="pending",
            to_status="approved",
            actor_id=b["user_id"],
            comment="B社内部の承認コメント",
        )
    )
    await db_session.flush()

    # 承認待ちの仕訳。承認・記帳を他テナントから叩けるかを見るために使う。
    pending = JournalHeader(
        company_id=b["company_id"],
        journal_number=f"BP-{uuid.uuid4().hex[:8]}",
        transaction_date=date(2026, 6, 16),
        summary="B社の承認待ち",
        approval_status="submitted",
        created_by=b["user_id"],
    )
    db_session.add(pending)
    await db_session.flush()
    db_session.add(
        JournalLine(
            journal_header_id=pending.journal_header_id,
            line_number=1,
            debit_credit="debit",
            account_id=account.account_id,
            amount=Decimal("220000"),
        )
    )
    await db_session.flush()

    # 職務分離により作成者は承認できないので、B に承認者役をもう1人置く。
    from app.core.security import create_access_token

    approver = User(
        tenant_id=b["tenant_id"],
        email=f"pb-appr-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="B承認者",
        role="admin",
        is_active=True,
    )
    db_session.add(approver)
    await db_session.flush()

    b["journal_header_id"] = header.journal_header_id
    b["pending_journal_id"] = pending.journal_header_id
    b["account_id"] = account.account_id
    b["approver_token"] = create_access_token(str(approver.user_id))
    return a, b


async def test_approval_history_of_another_tenant_is_not_readable(api, two_tenants):
    """他テナントの承認履歴（承認者・コメント）が読めないこと。"""
    a, b = two_tenants

    res = await api.get(
        f"/api/v1/approvals/history/{b['journal_header_id']}",
        headers={"Authorization": f"Bearer {a['token']}"},
    )

    assert res.status_code == 404, f"他テナントの承認履歴が読める ({res.status_code})"
    assert "承認コメント" not in res.text


async def test_the_owner_can_still_read_their_own_approval_history(api, two_tenants):
    """自テナントの承認履歴は読めること（塞ぎすぎていないこと）。"""
    _, b = two_tenants

    res = await api.get(
        f"/api/v1/approvals/history/{b['journal_header_id']}",
        headers={"Authorization": f"Bearer {b['token']}"},
    )

    assert res.status_code == 200, res.text
    assert len(res.json()) == 1
    assert res.json()[0]["comment"] == "B社内部の承認コメント"


async def test_sub_accounts_of_another_tenant_are_not_listable(api, two_tenants):
    """他テナントの勘定科目にぶら下がる補助科目が見えないこと。"""
    a, b = two_tenants

    res = await api.get(
        f"/api/v1/masters/sub-accounts/by-account/{b['account_id']}",
        headers={"Authorization": f"Bearer {a['token']}"},
    )

    assert res.status_code == 404, f"他テナントの補助科目が見える ({res.status_code})"
    assert "秘密" not in res.text


async def test_the_owner_can_still_list_their_own_sub_accounts(api, two_tenants):
    _, b = two_tenants

    res = await api.get(
        f"/api/v1/masters/sub-accounts/by-account/{b['account_id']}",
        headers={"Authorization": f"Bearer {b['token']}"},
    )

    assert res.status_code == 200, res.text
    assert [s["sub_account_name"] for s in res.json()] == ["B社の秘密の補助科目"]


# ---------------------------------------------------------------------------
# 承認ワークフロー: journal_header_id を本文で受け取る5経路
#
# こちらは読み取りではなく**書き込み**。他社の仕訳を承認・記帳できてしまうと、
# 相手の帳簿が第三者の操作で確定する。承認履歴には操作者として記録が残る。
# ---------------------------------------------------------------------------


async def test_another_tenants_journal_cannot_be_approved(api, two_tenants):
    a, b = two_tenants

    res = await api.post(
        "/api/v1/approvals/approve",
        json={"journal_header_id": str(b["pending_journal_id"]), "comment": "乗っ取り"},
        headers={"Authorization": f"Bearer {a['token']}"},
    )

    assert res.status_code == 404, f"他テナントの仕訳を承認できる ({res.status_code}) {res.text[:200]}"


async def test_another_tenants_journal_cannot_be_posted(api, two_tenants):
    a, b = two_tenants

    res = await api.post(
        "/api/v1/approvals/post",
        json={"journal_header_id": str(b["journal_header_id"])},
        headers={"Authorization": f"Bearer {a['token']}"},
    )

    assert res.status_code == 404, f"他テナントの仕訳を記帳できる ({res.status_code}) {res.text[:200]}"


async def test_another_tenants_journal_cannot_be_rejected(api, two_tenants):
    a, b = two_tenants

    res = await api.post(
        "/api/v1/approvals/reject",
        json={"journal_header_id": str(b["pending_journal_id"]), "comment": "差し戻し"},
        headers={"Authorization": f"Bearer {a['token']}"},
    )

    assert res.status_code == 404, f"他テナントの仕訳を差し戻せる ({res.status_code}) {res.text[:200]}"


async def test_another_tenants_journal_cannot_be_submitted(api, two_tenants):
    a, b = two_tenants

    res = await api.post(
        "/api/v1/approvals/submit",
        json={"journal_header_id": str(b["journal_header_id"])},
        headers={"Authorization": f"Bearer {a['token']}"},
    )

    assert res.status_code == 404, f"他テナントの仕訳を提出できる ({res.status_code}) {res.text[:200]}"


async def test_the_owner_can_still_approve_their_own_journal(api, two_tenants):
    """自テナントの承認は通ること（塞ぎすぎていないこと）。

    職務分離により作成者本人は承認できないので、同テナントの別ユーザーで叩く。
    """
    _, b = two_tenants
    res = await api.post(
        "/api/v1/approvals/approve",
        json={"journal_header_id": str(b["pending_journal_id"]), "comment": "承認"},
        headers={"Authorization": f"Bearer {b['approver_token']}"},
    )

    assert res.status_code == 200, res.text
    assert res.json()["approval_status"] == "approved"
