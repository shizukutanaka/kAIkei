"""自動仕訳学習の DB アダプタ（履歴からの学習と候補提示）。

学習器そのものの振る舞いは test_journal_learning.py（DB不要）で固定する。
ここでは実データとの接合部だけを見る:

- 確定済み（posted）の仕訳だけが学習対象になること（下書きは正解ではない）
- 候補の科目が ID・名称まで解決されて返ること
- **他社の仕訳が学習に混ざらないこと**（会計データの越境は漏えいそのもの）
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.models import Account, Company, JournalHeader, JournalLine, Tenant, User
from app.services.journal_learning import suggest_from_history, train_from_history

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

# (科目コード, 科目名, タイプ)
_ACCOUNTS = [
    ("1101", "現金預金", "asset"),
    ("2102", "未払金", "liability"),
    ("5201", "通信費", "expense"),
    ("5202", "地代家賃", "expense"),
]


@pytest_asyncio.fixture
async def books(db_session):
    tenant = Tenant(tenant_name="JL", tenant_code=f"JL-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()

    companies = {}
    for label in ("main", "other"):
        company = Company(
            tenant_id=tenant.tenant_id,
            company_name=f"学習商事 {label}",
            company_code=f"JL-{label}-{uuid.uuid4().hex[:6]}",
        )
        db_session.add(company)
        await db_session.flush()
        companies[label] = company

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

    accounts: dict[str, dict[str, Account]] = {}
    for label, company in companies.items():
        accounts[label] = {}
        for code, name, account_type in _ACCOUNTS:
            account = Account(
                company_id=company.company_id,
                account_code=code,
                account_name=name,
                account_type=account_type,
                debit_credit="debit" if account_type in ("asset", "expense") else "credit",
                is_active=True,
            )
            db_session.add(account)
            accounts[label][code] = account
    await db_session.flush()

    return {
        "db": db_session,
        "user_id": user.user_id,
        "companies": companies,
        "accounts": accounts,
    }


async def _post_journal(books, label: str, summary: str, debit_code: str, credit_code: str, *, status: str = "posted"):
    db = books["db"]
    company = books["companies"][label]
    accounts = books["accounts"][label]
    number = f"JRN-{uuid.uuid4().hex[:10]}"
    header = JournalHeader(
        company_id=company.company_id,
        journal_number=number,
        transaction_date=date(2026, 6, 15),
        voucher_type="transfer",
        summary=summary,
        approval_status=status,
        source_type="manual",
        created_by=books["user_id"],
    )
    db.add(header)
    await db.flush()
    db.add_all(
        [
            JournalLine(
                journal_header_id=header.journal_header_id,
                line_number=1,
                debit_credit="debit",
                account_id=accounts[debit_code].account_id,
                amount=Decimal("13200"),
                description=summary,
            ),
            JournalLine(
                journal_header_id=header.journal_header_id,
                line_number=2,
                debit_credit="credit",
                account_id=accounts[credit_code].account_id,
                amount=Decimal("13200"),
                description=summary,
            ),
        ]
    )
    await db.flush()
    return header


async def _seed_cloud_history(books, label: str = "main", count: int = 6):
    for month in range(1, count + 1):
        await _post_journal(
            books, label, f"クラウド利用料 請求書 2026-{month:03d} サーバ費用", "5201", "2102"
        )


async def test_suggestions_come_from_the_companys_own_posted_history(books):
    await _seed_cloud_history(books)

    result = await suggest_from_history(
        books["db"],
        books["companies"]["main"].company_id,
        description="クラウド利用料 請求書 2026-099 サーバ費用",
        amount=Decimal("13200"),
    )

    assert result["status"] == "ok"
    assert result["trained_examples"] == 6
    top = result["candidates"][0]
    assert [a["account_code"] for a in top["debit_accounts"]] == ["5201"]
    assert [a["account_code"] for a in top["credit_accounts"]] == ["2102"]
    # 科目は ID と名称まで解決されて返る（画面がそのまま使える形）
    assert top["debit_accounts"][0]["account_name"] == "通信費"
    assert top["debit_accounts"][0]["account_id"]
    assert top["reliable"] is True


async def test_draft_journals_are_not_learned(books):
    """下書きは「正解」ではないので学習対象にしない。"""
    await _seed_cloud_history(books)
    for i in range(6):
        await _post_journal(
            books, "main", f"事務所 家賃 下書き {i}", "5202", "1101", status="draft"
        )

    learner = await train_from_history(books["db"], books["companies"]["main"].company_id)
    assert learner.example_count == 6

    result = await suggest_from_history(
        books["db"],
        books["companies"]["main"].company_id,
        description="事務所 家賃 下書き 9",
    )
    assert result["status"] == "no_matching_history"


async def test_another_companys_history_never_leaks_in(books):
    """他社の仕訳パターンは、自社の候補にも学習件数にも現れない。"""
    await _seed_cloud_history(books, label="other")

    result = await suggest_from_history(
        books["db"],
        books["companies"]["main"].company_id,
        description="クラウド利用料 請求書 2026-099 サーバ費用",
        amount=Decimal("13200"),
    )

    assert result["status"] == "insufficient_data"
    assert result["trained_examples"] == 0
    assert result["candidates"] == []

    # 逆向きも同様に閉じていること
    other = await suggest_from_history(
        books["db"],
        books["companies"]["other"].company_id,
        description="クラウド利用料 請求書 2026-099 サーバ費用",
        amount=Decimal("13200"),
    )
    assert other["status"] == "ok"
    assert other["trained_examples"] == 6


async def test_posted_journals_are_counted_per_company(books):
    await _seed_cloud_history(books, label="main", count=6)
    await _seed_cloud_history(books, label="other", count=3)

    main_learner = await train_from_history(books["db"], books["companies"]["main"].company_id)
    other_learner = await train_from_history(books["db"], books["companies"]["other"].company_id)

    assert main_learner.example_count == 6
    assert other_learner.example_count == 3


async def test_accounts_used_by_candidates_still_exist(books):
    """候補が指す科目が実在することの裏取り（解決に使う select の形の確認）。"""
    await _seed_cloud_history(books)
    result = await suggest_from_history(
        books["db"],
        books["companies"]["main"].company_id,
        description="クラウド利用料 請求書 2026-100 サーバ費用",
    )
    top = result["candidates"][0]
    account_id = uuid.UUID(top["debit_accounts"][0]["account_id"])
    found = await books["db"].execute(select(Account).where(Account.account_id == account_id))
    assert found.scalar_one().account_code == "5201"
