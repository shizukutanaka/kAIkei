"""仕訳の作成・取得・取消（会計システムの中核）。

`POST /journals` は**必ず 500** を返していた。応答の `lines` を遅延ロード
しており、非同期セッションでは MissingGreenlet になる。取得・取消・承認・
記帳も同じ理由で壊れていた。

つまり仕訳を1件も登録できない状態だったが、1,600件超のテストは緑だった。
DBへ直接INSERTするテストばかりで、HTTP経路を通していなかったため。
実際にサーバを起動して初めて分かったので、経路ごと固定する。
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.models import Account, Company, Tenant, User

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def api(api_client):
    return api_client


@pytest_asyncio.fixture
async def books(db_session):
    from app.core.security import create_access_token

    tenant = Tenant(tenant_name="JL", tenant_code=f"JL-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    co = Company(
        tenant_id=tenant.tenant_id,
        company_name="仕訳商事",
        company_code=f"JL-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(co)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"jl-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="経理",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    cash = Account(
        company_id=co.company_id,
        account_code="1000",
        account_name="現金",
        account_type="asset",
        debit_credit="debit",
    )
    sales = Account(
        company_id=co.company_id,
        account_code="4000",
        account_name="売上",
        account_type="revenue",
        debit_credit="credit",
    )
    db_session.add_all([cash, sales])
    await db_session.flush()

    return {
        "company_id": co.company_id,
        "token": create_access_token(str(user.user_id)),
        "cash": cash,
        "sales": sales,
    }


def _auth(books):
    return {"Authorization": f"Bearer {books['token']}"}


async def _create(api, books, amount="110000"):
    return await api.post(
        "/api/v1/journals",
        json={
            "company_id": str(books["company_id"]),
            "transaction_date": str(date(2026, 6, 15)),
            "voucher_type": "transfer",
            "summary": "売上計上",
            "lines": [
                {
                    "line_number": 1,
                    "debit_credit": "debit",
                    "account_id": str(books["cash"].account_id),
                    "amount": amount,
                },
                {
                    "line_number": 2,
                    "debit_credit": "credit",
                    "account_id": str(books["sales"].account_id),
                    "amount": amount,
                },
            ],
        },
        headers=_auth(books),
    )


async def test_a_journal_can_be_created(api, books):
    """仕訳を登録できること。会計システムとして最低限の操作。"""
    res = await _create(api, books)

    assert res.status_code == 201, res.text


async def test_the_response_includes_its_lines(api, books):
    """応答に明細が含まれること。

    遅延ロードのままだと非同期セッションで MissingGreenlet になり、
    500 を返す（これが実際の壊れ方だった）。
    """
    body = (await _create(api, books)).json()

    assert len(body["lines"]) == 2
    assert {Decimal(line["amount"]) for line in body["lines"]} == {Decimal("110000")}


async def test_a_journal_can_be_fetched(api, books):
    created = (await _create(api, books)).json()

    res = await api.get(f"/api/v1/journals/{created['journal_header_id']}", headers=_auth(books))

    assert res.status_code == 200, res.text
    assert len(res.json()["lines"]) == 2


async def test_journals_are_listed_with_their_lines(api, books):
    """一覧も明細を含む。0件のときだけ通る状態になっていた。"""
    await _create(api, books)

    res = await api.get(
        "/api/v1/journals",
        params={"company_id": str(books["company_id"])},
        headers=_auth(books),
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 1
    assert len(body["items"][0]["lines"]) == 2


async def test_a_journal_can_be_voided(api, books):
    created = (await _create(api, books)).json()

    res = await api.put(
        f"/api/v1/journals/{created['journal_header_id']}/void", headers=_auth(books)
    )

    assert res.status_code == 200, res.text
    assert res.json()["is_voided"] is True
    assert len(res.json()["lines"]) == 2


async def test_voiding_twice_is_rejected(api, books):
    created = (await _create(api, books)).json()
    jid = created["journal_header_id"]
    assert (await api.put(f"/api/v1/journals/{jid}/void", headers=_auth(books))).status_code == 200

    again = await api.put(f"/api/v1/journals/{jid}/void", headers=_auth(books))

    assert again.status_code == 409


async def test_unbalanced_entry_is_rejected(api, books):
    """貸借が一致しない仕訳は受け付けないこと。"""
    res = await api.post(
        "/api/v1/journals",
        json={
            "company_id": str(books["company_id"]),
            "transaction_date": str(date(2026, 6, 15)),
            "voucher_type": "transfer",
            "summary": "不一致",
            "lines": [
                {
                    "line_number": 1,
                    "debit_credit": "debit",
                    "account_id": str(books["cash"].account_id),
                    "amount": "100",
                },
                {
                    "line_number": 2,
                    "debit_credit": "credit",
                    "account_id": str(books["sales"].account_id),
                    "amount": "200",
                },
            ],
        },
        headers=_auth(books),
    )

    assert res.status_code in (400, 422), res.text


@pytest_asyncio.fixture
async def approver(db_session, books):
    """同じテナントの別ユーザー。職務分離により作成者は承認できない。"""
    from sqlalchemy import select

    from app.core.security import create_access_token

    company = (
        await db_session.execute(select(Company).where(Company.company_id == books["company_id"]))
    ).scalar_one()
    user = User(
        tenant_id=company.tenant_id,
        email=f"ap-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="承認者",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return {"Authorization": f"Bearer {create_access_token(str(user.user_id))}"}


async def _submit(api, books, journal_header_id):
    """作成者が承認待ちに提出する（draft → submitted）。"""
    return await api.post(
        "/api/v1/approvals/submit",
        json={"journal_header_id": journal_header_id},
        headers=_auth(books),
    )


async def test_the_creator_cannot_approve_their_own_journal(api, books):
    """職務分離（SoD）が効いていること。"""
    created = (await _create(api, books)).json()
    assert (await _submit(api, books, created["journal_header_id"])).status_code == 200

    res = await api.put(
        f"/api/v1/journals/{created['journal_header_id']}/approve", headers=_auth(books)
    )

    assert res.status_code == 403


async def test_a_journal_can_be_approved_and_posted(api, books, approver):
    """承認・記帳が応答を返せること（明細の遅延ロードで500にならない）。"""
    created = (await _create(api, books)).json()
    jid = created["journal_header_id"]
    assert (await _submit(api, books, jid)).status_code == 200

    approved = await api.put(f"/api/v1/journals/{jid}/approve", headers=approver)
    assert approved.status_code == 200, approved.text
    assert len(approved.json()["lines"]) == 2

    posted = await api.put(f"/api/v1/journals/{jid}/post", headers=approver)
    assert posted.status_code == 200, posted.text
    assert len(posted.json()["lines"]) == 2


async def test_approval_cannot_skip_submission(api, books, approver):
    """draft のまま承認できないこと。

    以前 `/journals/{id}/approve` には `draft/waiting` を受け付ける別実装があり、
    提出を飛ばして承認できた（`waiting` は他のどこにも無い幽霊ステータス）。
    状態機械は draft → submitted → approved → posted の1系統だけにする。
    """
    created = (await _create(api, books)).json()

    res = await api.put(
        f"/api/v1/journals/{created['journal_header_id']}/approve", headers=approver
    )

    assert res.status_code == 400
    assert "draft" in res.json()["detail"]


async def test_approving_via_journals_router_leaves_an_audit_trail(api, books, approver):
    """どちらの経路で承認しても承認履歴（ApprovalLog）が残ること。

    以前の別実装は履歴を書かず、`/journals/{id}/approve` で承認すると
    「誰がいつ承認したか」が残らなかった。会計システムとして許容できない。
    """
    created = (await _create(api, books)).json()
    jid = created["journal_header_id"]
    assert (await _submit(api, books, jid)).status_code == 200
    assert (await api.put(f"/api/v1/journals/{jid}/approve", headers=approver)).status_code == 200
    assert (await api.put(f"/api/v1/journals/{jid}/post", headers=approver)).status_code == 200

    history = await api.get(f"/api/v1/approvals/history/{jid}", headers=_auth(books))

    assert history.status_code == 200, history.text
    assert [log["action"] for log in history.json()] == ["submit", "approve", "post"]
