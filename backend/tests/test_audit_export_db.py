"""監査エクスポート（総勘定元帳・監査ログのZIP出力）。

このエンドポイントは**2回続けて列名の誤りで壊れていた**。

1. `JournalHeader.journal_date`（正しくは `transaction_date`）
2. `JournalLine.debit_amount` / `credit_amount`（実際は `debit_credit` と `amount`）

1つ目を直したとき、疎通確認は通っていた。しかし会社にデータが無かったため
取得が0件になり、**行を処理するループに一度も入らなかった**。2つ目は実データで
初めて露見した。

税務調査に出す資料なので、出力できないことに気付けない状態は避けたい。
実データを入れた状態で、中身まで確認する。
"""
import io
import uuid
import zipfile
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.models import Account, Company, JournalHeader, JournalLine, Tenant, User

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

YEAR = 2026


@pytest_asyncio.fixture
async def api(api_client):
    return api_client


@pytest_asyncio.fixture
async def books(db_session):
    from app.core.security import create_access_token

    tenant = Tenant(tenant_name="AX", tenant_code=f"AX-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    co = Company(
        tenant_id=tenant.tenant_id,
        company_name="監査商事",
        company_code=f"AX-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(co)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"ax-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="監査",
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

    header = JournalHeader(
        company_id=co.company_id,
        journal_number="JRN-00000001",
        transaction_date=date(YEAR, 6, 15),
        summary="売上計上",
        approval_status="approved",
        created_by=user.user_id,
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

    return {
        "company_id": co.company_id,
        "token": create_access_token(str(user.user_id)),
    }


async def _export(api, books):
    return await api.get(
        "/api/v1/audit/export",
        params={"company_id": str(books["company_id"]), "fiscal_year": YEAR},
        headers={"Authorization": f"Bearer {books['token']}"},
    )


async def test_the_export_succeeds_with_real_data(api, books):
    """データがある状態で出力できること（空の会社では素通りしていた）。"""
    res = await _export(api, books)

    assert res.status_code == 200, res.text


async def test_the_export_is_a_readable_zip(api, books):
    res = await _export(api, books)

    archive = zipfile.ZipFile(io.BytesIO(res.content))
    assert archive.testzip() is None
    assert "general_ledger.csv" in archive.namelist()


async def test_the_ledger_contains_the_journal(api, books):
    """明細の中身まで出ていること。列名を間違えると空欄や例外になる。"""
    res = await _export(api, books)

    archive = zipfile.ZipFile(io.BytesIO(res.content))
    ledger = archive.read("general_ledger.csv").decode("utf-8-sig")

    assert "JRN-00000001" in ledger
    assert "2026-06-15" in ledger, "取引日が出ていない"
    assert "110000" in ledger, "金額が出ていない"


async def test_debit_and_credit_are_in_separate_columns(api, books):
    """借方・貸方が別の列に振り分けられること。

    `debit_credit` を見ずに書くと、両方に同じ額が入るか空になる。
    """
    res = await _export(api, books)
    archive = zipfile.ZipFile(io.BytesIO(res.content))
    rows = [
        r.split(",")
        for r in archive.read("general_ledger.csv").decode("utf-8-sig").splitlines()
        if "JRN-00000001" in r
    ]

    assert len(rows) == 2, "借方・貸方の2行が出ていない"
    debit_col = {r[4] for r in rows}
    credit_col = {r[5] for r in rows}
    assert debit_col == {"110000.0000", "0"}, f"借方列が不正: {debit_col}"
    assert credit_col == {"110000.0000", "0"}, f"貸方列が不正: {credit_col}"
