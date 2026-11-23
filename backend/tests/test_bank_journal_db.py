"""銀行明細 → 仕訳ドラフト変換の DB テスト。

中核フロー（明細を取り込む → 学習候補で相手科目を決める → ドラフトを作る →
確定した仕訳が次の学習データになる）を実データとの接合部で固定する。
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.models import Account, Company, JournalHeader, JournalLine, Tenant, User
from app.services import bank_journal, bank_reconciliation

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

_ACCOUNTS = [
    ("1101", "普通預金", "asset"),
    ("5201", "通信費", "expense"),
    ("5202", "地代家賃", "expense"),
]


@pytest_asyncio.fixture
async def books(db_session):
    tenant = Tenant(tenant_name="BJ", tenant_code=f"BJ-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    company = Company(
        tenant_id=tenant.tenant_id,
        company_name="明細商事",
        company_code=f"BJ-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(company)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"bj-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="経理",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    accounts = {}
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
        accounts[code] = account
    await db_session.flush()
    return {
        "db": db_session,
        "tenant_id": tenant.tenant_id,
        "company_id": company.company_id,
        "user_id": user.user_id,
        "accounts": accounts,
    }


async def _seed_posted_journal(books, number: int, debit_code: str, credit_code: str, summary: str):
    db = books["db"]
    header = JournalHeader(
        company_id=books["company_id"],
        journal_number=f"SEED-{number}",
        transaction_date=date(2026, 3, number),
        summary=summary,
        approval_status="posted",
        created_by=books["user_id"],
    )
    db.add(header)
    await db.flush()
    for line_number, (side, code) in enumerate((("debit", debit_code), ("credit", credit_code)), start=1):
        db.add(JournalLine(
            journal_header_id=header.journal_header_id,
            line_number=line_number,
            debit_credit=side,
            account_id=books["accounts"][code].account_id,
            amount=Decimal("5000"),
            description=summary,
        ))
    await db.flush()
    return header


async def _import_line(books, csv_row: str):
    csv_text = "取引日,入金額,出金額,残高,摘要,振込人名カナ\n" + csv_row
    lines = await bank_reconciliation.import_statement_csv(
        books["db"], books["tenant_id"], books["company_id"], csv_text
    )
    assert len(lines) == 1
    return lines[0]


async def test_suggest_and_create_draft_then_feedback_loop(books):
    db = books["db"]
    bank_id = books["accounts"]["1101"].account_id
    # 過去に「通信費」を普通預金から払った確定仕訳を5件入れる（学習の下限以上）。
    for i in range(1, 6):
        await _seed_posted_journal(books, i, "5201", "1101", "通信費 NTT")

    line = await _import_line(books, "2026/04/15,,5000,100000,通信費 NTT,\n")

    suggestion = await bank_journal.suggest_for_bank_line(db, books["company_id"], line.bank_statement_line_id, bank_id)
    assert suggestion["status"] == "ok"
    assert len(suggestion["candidates"]) == 1
    candidate = suggestion["candidates"][0]
    assert candidate["account_code"] == "5201"
    assert candidate["matches_bank_account"] is True
    assert candidate["reliable"] is True

    header = await bank_journal.create_journal_from_bank_line(
        db,
        company_id=books["company_id"],
        line_id=line.bank_statement_line_id,
        bank_account_id=bank_id,
        counterpart_account_id=books["accounts"]["5201"].account_id,
        created_by=books["user_id"],
    )
    assert header.approval_status == "draft"
    assert header.source_type == "bank_statement"
    by_side = {jl.debit_credit: jl for jl in header.lines}
    assert by_side["debit"].account_id == books["accounts"]["5201"].account_id
    assert by_side["credit"].account_id == bank_id
    assert by_side["debit"].amount == Decimal("5000")

    refreshed = await bank_reconciliation.list_statement_lines(db, books["company_id"], reconciled=True)
    assert len(refreshed) == 1
    assert refreshed[0].reconciled_journal_line_id == by_side["credit"].journal_line_id

    # 確定すると学習データが増え、次の同種明細にも候補が出る（修正が学習に返る）。
    header.approval_status = "posted"
    await db.commit()
    line2 = await _import_line(books, "2026/05/15,,5000,95000,通信費 NTT,\n")
    suggestion2 = await bank_journal.suggest_for_bank_line(
        db, books["company_id"], line2.bank_statement_line_id, bank_id
    )
    assert suggestion2["trained_examples"] == 6
    assert suggestion2["candidates"][0]["account_code"] == "5201"


async def test_create_rejects_already_reconciled(books):
    bank_id = books["accounts"]["1101"].account_id
    line = await _import_line(books, "2026/04/15,,5000,100000,家賃,\n")
    await bank_journal.create_journal_from_bank_line(
        books["db"],
        company_id=books["company_id"],
        line_id=line.bank_statement_line_id,
        bank_account_id=bank_id,
        counterpart_account_id=books["accounts"]["5202"].account_id,
        created_by=books["user_id"],
    )
    with pytest.raises(bank_journal.AlreadyReconciledError):
        await bank_journal.create_journal_from_bank_line(
            books["db"],
            company_id=books["company_id"],
            line_id=line.bank_statement_line_id,
            bank_account_id=bank_id,
            counterpart_account_id=books["accounts"]["5202"].account_id,
            created_by=books["user_id"],
        )


async def test_create_rejects_same_account_for_both_sides(books):
    bank_id = books["accounts"]["1101"].account_id
    line = await _import_line(books, "2026/04/15,5000,,100000,入金,\n")
    with pytest.raises(ValueError, match="同じ科目"):
        await bank_journal.create_journal_from_bank_line(
            books["db"],
            company_id=books["company_id"],
            line_id=line.bank_statement_line_id,
            bank_account_id=bank_id,
            counterpart_account_id=bank_id,
            created_by=books["user_id"],
        )


async def test_suggest_without_history_reports_insufficient_data(books):
    bank_id = books["accounts"]["1101"].account_id
    line = await _import_line(books, "2026/04/15,,5000,100000,通信費 NTT,\n")
    suggestion = await bank_journal.suggest_for_bank_line(
        books["db"], books["company_id"], line.bank_statement_line_id, bank_id
    )
    assert suggestion["status"] == "insufficient_data"
    assert suggestion["candidates"] == []
