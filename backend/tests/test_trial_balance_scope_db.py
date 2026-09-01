"""試算表が含めてよい仕訳だけを集計していること。

試算表は決算と申告の土台になる。取り消した仕訳や、まだ発生していない
（基準日より後の）仕訳が混ざると、**そのまま誤った決算書になる**。

集計クエリは会社・期間・取消・削除の条件を `JournalHeader` への
**外部結合の結合条件**に書いている。外部結合は条件に合わない行を
落とすのではなく、結合先の列を NULL にするだけなので、
`JournalLine` の金額は条件に関係なく合計に入る。
（`WHERE` に書くか、内部結合にする必要がある。）
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.models import Account, Company, JournalHeader, JournalLine, Tenant, User

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

AS_OF = date(2026, 6, 30)


@pytest_asyncio.fixture
async def api(api_client):
    return api_client


@pytest_asyncio.fixture
async def books(db_session):
    """基準日以前の正常な仕訳1件と、含めてはいけない仕訳3件を作る。"""
    from app.core.security import create_access_token

    tenant = Tenant(tenant_name="TB", tenant_code=f"TB-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    company = Company(
        tenant_id=tenant.tenant_id,
        company_name="試算表商事",
        company_code=f"TB-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(company)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"tb-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="経理",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    cash = Account(
        company_id=company.company_id, account_code="1000", account_name="現金",
        account_type="asset", debit_credit="debit", is_active=True,
    )
    sales = Account(
        company_id=company.company_id, account_code="4000", account_name="売上",
        account_type="revenue", debit_credit="credit", is_active=True,
    )
    db_session.add_all([cash, sales])
    await db_session.flush()

    async def add_journal(number, when, amount, *, voided=False, deleted=False):
        header = JournalHeader(
            company_id=company.company_id,
            journal_number=f"{number}-{uuid.uuid4().hex[:6]}",
            transaction_date=when,
            summary=number,
            approval_status="approved",
            created_by=user.user_id,
            is_voided=voided,
            is_deleted=deleted,
        )
        db_session.add(header)
        await db_session.flush()
        db_session.add_all([
            JournalLine(
                journal_header_id=header.journal_header_id, line_number=1,
                debit_credit="debit", account_id=cash.account_id, amount=Decimal(amount),
            ),
            JournalLine(
                journal_header_id=header.journal_header_id, line_number=2,
                debit_credit="credit", account_id=sales.account_id, amount=Decimal(amount),
            ),
        ])
        await db_session.flush()

    await add_journal("NORMAL", date(2026, 6, 15), "100000")
    await add_journal("VOIDED", date(2026, 6, 16), "500000", voided=True)
    await add_journal("FUTURE", date(2026, 12, 31), "700000")
    await add_journal("DELETED", date(2026, 6, 17), "300000", deleted=True)

    return {
        "company_id": company.company_id,
        "token": create_access_token(str(user.user_id)),
    }


async def _cash_row(api, books):
    res = await api.get(
        "/api/v1/reports/trial-balance",
        params={"company_id": str(books["company_id"]), "as_of": AS_OF.isoformat()},
        headers={"Authorization": f"Bearer {books['token']}"},
    )
    assert res.status_code == 200, res.text
    rows = {r["account_code"]: r for r in res.json()["accounts"]}
    return rows["1000"], res.json()


async def test_only_the_valid_journal_is_counted(api, books):
    """基準日以前の有効な仕訳だけが計上されること。

    取消50万・期間外70万・削除30万が混ざると、現金の借方は100,000にならない。
    """
    cash, _ = await _cash_row(api, books)

    assert Decimal(cash["debit_total"]) == Decimal("100000"), (
        f"現金の借方が {cash['debit_total']}。取消・期間外・削除の仕訳が混ざっている"
    )


async def test_a_voided_journal_is_excluded(api, books):
    """取り消した仕訳が残っていないこと。"""
    cash, _ = await _cash_row(api, books)

    assert Decimal("500000") not in (
        Decimal(cash["debit_total"]),
        Decimal(cash["debit_total"]) - Decimal("100000"),
    ), "取消済みの仕訳が計上されている"
    assert Decimal(cash["debit_total"]) < Decimal("500000"), "取消済みの仕訳が計上されている"


async def test_a_future_journal_is_excluded(api, books):
    """基準日より後の仕訳が計上されないこと。

    含まれると「いつ時点の試算表なのか」が意味を失う。
    """
    cash, _ = await _cash_row(api, books)

    assert Decimal(cash["debit_total"]) < Decimal("700000"), "基準日より後の仕訳が計上されている"


async def test_the_trial_balance_itself_balances(api, books):
    """試算表の借方合計と貸方合計が一致すること。"""
    _, body = await _cash_row(api, books)

    assert Decimal(body["total_debit"]) == Decimal(body["total_credit"]), (
        f"試算表が合わない: 借方={body['total_debit']} 貸方={body['total_credit']}"
    )


async def test_accounts_with_no_activity_still_appear(api, books):
    """取引の無い勘定科目が試算表から消えないこと。

    結合を内部結合にして直すと、仕訳の無い科目ごと落ちてしまう。
    ここでは「ヘッダが条件に合ったときだけ金額を数える」形で直しているので、
    科目は残り、金額が0になる。
    """
    res = await api.get(
        "/api/v1/reports/trial-balance",
        params={"company_id": str(books["company_id"]), "as_of": "2026-01-31"},
        headers={"Authorization": f"Bearer {books['token']}"},
    )

    assert res.status_code == 200, res.text
    rows = {r["account_code"]: r for r in res.json()["accounts"]}
    assert "1000" in rows and "4000" in rows, "取引の無い期間で科目が消えている"
    assert Decimal(rows["1000"]["debit_total"]) == Decimal("0")


# ---------------------------------------------------------------------------
# 同じ集計は損益計算書・貸借対照表・KPI・キャッシュフローとその各エクスポートが
# 共有している（_get_account_balances）。試算表だけ直しても意味が無い。
# ---------------------------------------------------------------------------


async def test_the_income_statement_excludes_the_same_journals(api, books):
    """損益計算書にも取消・期間外が入らないこと。"""
    res = await api.get(
        "/api/v1/reports/income-statement",
        params={"company_id": str(books["company_id"]), "as_of": AS_OF.isoformat()},
        headers={"Authorization": f"Bearer {books['token']}"},
    )

    assert res.status_code == 200, res.text
    revenue = Decimal(str(res.json()["total_revenue"]))
    assert revenue == Decimal("100000"), f"売上が {revenue}。取消・期間外が混ざっている"


async def test_the_balance_sheet_excludes_the_same_journals(api, books):
    """貸借対照表にも取消・期間外が入らないこと。"""
    res = await api.get(
        "/api/v1/reports/balance-sheet",
        params={"company_id": str(books["company_id"]), "as_of": AS_OF.isoformat()},
        headers={"Authorization": f"Bearer {books['token']}"},
    )

    assert res.status_code == 200, res.text
    assets = Decimal(str(res.json()["total_assets"]))
    assert assets == Decimal("100000"), f"資産合計が {assets}。取消・期間外が混ざっている"


async def test_the_trial_balance_csv_matches_the_json(api, books):
    """CSVエクスポートも同じ数字になること（別のクエリを持っている）。"""
    res = await api.get(
        "/api/v1/reports/trial-balance/export",
        params={"company_id": str(books["company_id"]), "as_of": AS_OF.isoformat()},
        headers={"Authorization": f"Bearer {books['token']}"},
    )

    assert res.status_code == 200, res.text
    cash_row = [r for r in res.text.splitlines() if r.startswith("1000,")]
    assert cash_row, f"現金の行が無い:\n{res.text[:300]}"
    assert "1600000" not in cash_row[0], f"取消・期間外が混ざっている: {cash_row[0]}"
    assert "100000" in cash_row[0], f"正しい金額が出ていない: {cash_row[0]}"
