from datetime import date
from decimal import Decimal

import pytest

from app.models.models import Account, JournalHeader, JournalLine
from app.services import bank_reconciliation

pytestmark = pytest.mark.db


async def _seed_bank_journal_line(db_session, company_id, user_id, amount, txn_date, desc):
    account = Account(
        company_id=company_id, account_code="1120", account_name="普通預金",
        account_type="asset", debit_credit="debit",
    )
    db_session.add(account)
    await db_session.flush()
    header = JournalHeader(
        company_id=company_id, journal_number="J-0001", transaction_date=txn_date, created_by=user_id,
    )
    db_session.add(header)
    await db_session.flush()
    line = JournalLine(
        journal_header_id=header.journal_header_id, line_number=1, debit_credit="debit",
        account_id=account.account_id, amount=amount, description=desc,
    )
    db_session.add(line)
    await db_session.flush()
    return account.account_id, line.journal_line_id


async def test_import_and_auto_reconcile(db_session, seed_company):
    tid, cid, uid = seed_company["tenant_id"], seed_company["company_id"], seed_company["user_id"]
    account_id, jline_id = await _seed_bank_journal_line(
        db_session, cid, uid, Decimal("10000"), date(2026, 4, 15), "カイケイ",
    )

    csv_text = (
        "取引日,入金額,出金額,残高,摘要,振込人名カナ\n"
        "2026/04/15,\"10,000\",,\"110,000\",振込入金,カイケイ\n"
    )
    lines = await bank_reconciliation.import_statement_csv(db_session, tid, cid, csv_text)
    assert len(lines) == 1
    assert lines[0].is_reconciled is False

    result = await bank_reconciliation.auto_reconcile(db_session, cid, account_id)
    assert result["matched"] == 1

    reconciled = await bank_reconciliation.list_statement_lines(db_session, cid, reconciled=True)
    assert len(reconciled) == 1
    assert reconciled[0].reconciled_journal_line_id == jline_id

    # unmatch reverses it
    await bank_reconciliation.unmatch(db_session, cid, reconciled[0].bank_statement_line_id)
    assert await bank_reconciliation.list_statement_lines(db_session, cid, reconciled=True) == []
