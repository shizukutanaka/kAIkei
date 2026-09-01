"""自動生成される仕訳の貸借が必ず一致すること。

複式簿記では借方合計と貸方合計が必ず一致する。一致しない仕訳が帳簿に入ると
**試算表が合わなくなり、決算も申告もできない**。

請求書・入金・経費精算・給与・賞与・減価償却の仕訳は自動生成され、
API の検証（`POST /journals` の貸借チェック）を**通らずに直接書き込まれる**。
金額は呼び出し元が別々の引数で渡すため、渡された値が食い違えばそのまま
不整合な仕訳になる。

呼び出し元は現状いずれも整合した値を渡している（請求書は明細から算出、
給与は `net_pay = total_gross - total_deductions`）。しかしそれは呼び出し元の
実装に依存しているだけで、生成器側では何も保証していなかった。会計システムで
最も壊れてはいけない性質なので、書き込む直前で確かめる。
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.models import Account, Company, JournalLine, Tenant, User
from app.services import auto_journal

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

# 生成器が使う勘定科目（type, code接頭辞, 名前）。
_ACCOUNTS = [
    ("asset", "11", "売掛金"),
    ("asset", "12", "現金預金"),
    ("revenue", "41", "売上"),
    ("liability", "21", "仮受消費税"),
    ("liability", "22", "預り金"),
    ("expense", "51", "給与手当"),
    ("expense", "52", "旅費交通費"),
    ("expense", "53", "減価償却費"),
    ("asset", "15", "減価償却累計額"),
]


@pytest_asyncio.fixture
async def books(db_session):
    tenant = Tenant(tenant_name="AJ", tenant_code=f"AJ-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    company = Company(
        tenant_id=tenant.tenant_id,
        company_name="自動仕訳商事",
        company_code=f"AJ-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(company)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"aj-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="経理",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    for account_type, code, name in _ACCOUNTS:
        db_session.add(
            Account(
                company_id=company.company_id,
                account_code=f"{code}00",
                account_name=name,
                account_type=account_type,
                debit_credit="debit" if account_type in ("asset", "expense") else "credit",
                is_active=True,
            )
        )
    await db_session.flush()
    return {"company_id": company.company_id, "user_id": user.user_id, "db": db_session}


async def _lines_of(db_session, header) -> list[JournalLine]:
    from sqlalchemy import select

    result = await db_session.execute(
        select(JournalLine).where(JournalLine.journal_header_id == header.journal_header_id)
    )
    return list(result.scalars().all())


def _totals(lines):
    debit = sum((line.amount for line in lines if line.debit_credit == "debit"), Decimal("0"))
    credit = sum((line.amount for line in lines if line.debit_credit == "credit"), Decimal("0"))
    return debit, credit


async def _assert_balanced(db_session, header, label):
    lines = await _lines_of(db_session, header)
    assert lines, f"{label}: 明細が1件も作られていない"
    debit, credit = _totals(lines)
    assert debit == credit, f"{label}: 借方={debit} 貸方={credit} で一致しない"


async def test_the_invoice_issue_journal_balances(books):
    """(借) 売掛金 / (貸) 売上 + 仮受消費税"""
    header = await auto_journal.generate_invoice_issue_journal(
        books["db"],
        company_id=books["company_id"],
        invoice_number="INV-001",
        invoice_date=date(2026, 6, 15),
        subtotal=Decimal("100000"),
        tax_amount=Decimal("10000"),
        total_amount=Decimal("110000"),
        created_by=books["user_id"],
    )

    await _assert_balanced(books["db"], header, "請求書発行")


async def test_the_invoice_issue_journal_balances_without_tax(books):
    """免税・非課税で消費税0のとき、税の行が省かれても一致すること。"""
    header = await auto_journal.generate_invoice_issue_journal(
        books["db"],
        company_id=books["company_id"],
        invoice_number="INV-002",
        invoice_date=date(2026, 6, 15),
        subtotal=Decimal("100000"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("100000"),
        created_by=books["user_id"],
    )

    await _assert_balanced(books["db"], header, "請求書発行（税なし）")


async def test_the_payroll_journal_balances(books):
    """(借) 給与費用 / (貸) 現金預金(差引) + 預り金(控除額)"""
    header = await auto_journal.generate_payroll_journal(
        books["db"],
        company_id=books["company_id"],
        payroll_year=2026,
        payroll_month=6,
        total_gross=Decimal("400000"),
        total_deductions=Decimal("72000"),
        net_pay=Decimal("328000"),
        created_by=books["user_id"],
    )

    await _assert_balanced(books["db"], header, "給与支払")


async def test_an_inconsistent_payroll_journal_is_refused(books):
    """差引が合わない給与仕訳は作れないこと。

    これが通ってしまうと、試算表が合わない帳簿ができあがる。
    """
    with pytest.raises(ValueError, match="貸借が一致しない"):
        await auto_journal.generate_payroll_journal(
            books["db"],
            company_id=books["company_id"],
            payroll_year=2026,
            payroll_month=7,
            total_gross=Decimal("400000"),
            total_deductions=Decimal("72000"),
            net_pay=Decimal("300000"),  # 本来は 328,000
            created_by=books["user_id"],
        )


async def test_an_inconsistent_invoice_journal_is_refused(books):
    """合計が内訳と合わない請求書仕訳は作れないこと。"""
    with pytest.raises(ValueError, match="貸借が一致しない"):
        await auto_journal.generate_invoice_issue_journal(
            books["db"],
            company_id=books["company_id"],
            invoice_number="INV-BAD",
            invoice_date=date(2026, 6, 15),
            subtotal=Decimal("100000"),
            tax_amount=Decimal("10000"),
            total_amount=Decimal("120000"),  # 本来は 110,000
            created_by=books["user_id"],
        )


def test_every_generator_goes_through_the_check():
    """生成器が増えても検証を通ること。

    新しい生成器を足したときに `_add_balanced` を通し忘れると、
    そこだけ素通りする。件数で気付けるようにしておく。
    """
    import inspect

    source = inspect.getsource(auto_journal)
    generators = [n for n in dir(auto_journal) if n.startswith("generate_")]

    # 定義行 (`def _add_balanced(db...`) を数えないよう、呼び出しの形で数える。
    calls = source.count("    _add_balanced(db, lines,")

    assert len(generators) >= 6, f"生成器が {len(generators)} 個しか見つからない"
    assert calls == len(generators), (
        f"生成器 {len(generators)} 個に対して検証の呼び出しが {calls} 箇所しかない"
    )
