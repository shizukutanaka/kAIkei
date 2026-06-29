"""Service for auto-generating journal entries from invoices and expenses."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Account, JournalHeader, JournalLine


async def _find_account(
    db: AsyncSession,
    company_id: UUID,
    account_type: str,
    account_code_hint: str | None = None,
) -> Account:
    """Find an account by type, optionally by code prefix."""
    query = (
        select(Account)
        .where(
            Account.company_id == company_id,
            Account.account_type == account_type,
            Account.is_active.is_(True),
            Account.is_deleted.is_(False),
        )
        .order_by(Account.account_code)
    )
    if account_code_hint:
        query = query.where(Account.account_code.like(f"{account_code_hint}%")).limit(1)
    else:
        query = query.limit(1)

    result = await db.execute(query)
    account = result.scalar_one_or_none()
    if not account:
        raise ValueError(f"Account not found: type={account_type}, code_hint={account_code_hint}")
    return account


async def _next_journal_number(db: AsyncSession, company_id: UUID) -> str:
    count_result = await db.execute(
        select(func.count()).select_from(JournalHeader).where(JournalHeader.company_id == company_id)
    )
    count = count_result.scalar() or 0
    return f"JRN-{count + 1:08d}"


async def generate_invoice_issue_journal(
    db: AsyncSession,
    *,
    company_id: UUID,
    invoice_number: str,
    invoice_date,
    subtotal: Decimal,
    tax_amount: Decimal,
    total_amount: Decimal,
    created_by: UUID,
) -> JournalHeader:
    """売上仕訳: (借) 売掛金 / (貸) 売上 + 消費税"""
    ar_account = await _find_account(db, company_id, "asset", "11")  # 売掛金
    sales_account = await _find_account(db, company_id, "revenue", "41")  # 売上
    tax_account = await _find_account(db, company_id, "liability", "21")  # 仮受消費税

    journal_number = await _next_journal_number(db, company_id)

    header = JournalHeader(
        company_id=company_id,
        journal_number=journal_number,
        transaction_date=invoice_date,
        voucher_type="sales",
        summary=f"請求書発行: {invoice_number}",
        approval_status="draft",
        source_type="invoice",
        created_by=created_by,
    )
    db.add(header)
    await db.flush()

    lines: list[JournalLine] = []
    line_no = 1

    # (借) 売掛金 — total
    lines.append(JournalLine(
        journal_header_id=header.journal_header_id,
        line_number=line_no,
        debit_credit="debit",
        account_id=ar_account.account_id,
        amount=total_amount,
        description=f"請求書 {invoice_number}",
    ))
    line_no += 1

    # (貸) 売上 — subtotal
    lines.append(JournalLine(
        journal_header_id=header.journal_header_id,
        line_number=line_no,
        debit_credit="credit",
        account_id=sales_account.account_id,
        amount=subtotal,
        description=f"売上 {invoice_number}",
    ))
    line_no += 1

    # (貸) 仮受消費税 — tax_amount (only if non-zero)
    if tax_amount > 0:
        lines.append(JournalLine(
            journal_header_id=header.journal_header_id,
            line_number=line_no,
            debit_credit="credit",
            account_id=tax_account.account_id,
            amount=tax_amount,
            description=f"消費税 {invoice_number}",
        ))

    for ln in lines:
        db.add(ln)

    await db.flush()
    return header


async def generate_invoice_payment_journal(
    db: AsyncSession,
    *,
    company_id: UUID,
    invoice_number: str,
    payment_date,
    total_amount: Decimal,
    created_by: UUID,
) -> JournalHeader:
    """入金仕訳: (借) 現金/普通預金 / (貸) 売掛金"""
    cash_account = await _find_account(db, company_id, "asset", "12")  # 現金/預金
    ar_account = await _find_account(db, company_id, "asset", "11")  # 売掛金

    journal_number = await _next_journal_number(db, company_id)

    header = JournalHeader(
        company_id=company_id,
        journal_number=journal_number,
        transaction_date=payment_date,
        voucher_type="receipt",
        summary=f"入金: {invoice_number}",
        approval_status="draft",
        source_type="invoice_payment",
        created_by=created_by,
    )
    db.add(header)
    await db.flush()

    # (借) 現金/預金
    db.add(JournalLine(
        journal_header_id=header.journal_header_id,
        line_number=1,
        debit_credit="debit",
        account_id=cash_account.account_id,
        amount=total_amount,
        description=f"入金 {invoice_number}",
    ))
    # (貸) 売掛金
    db.add(JournalLine(
        journal_header_id=header.journal_header_id,
        line_number=2,
        debit_credit="credit",
        account_id=ar_account.account_id,
        amount=total_amount,
        description=f"入金消込 {invoice_number}",
    ))

    await db.flush()
    return header


async def generate_expense_payment_journal(
    db: AsyncSession,
    *,
    company_id: UUID,
    report_title: str,
    payment_date,
    total_amount: Decimal,
    created_by: UUID,
) -> JournalHeader:
    """経費支払仕訳: (借) 経費(費用) / (貸) 現金"""
    expense_account = await _find_account(db, company_id, "expense", "52")  # 経費
    cash_account = await _find_account(db, company_id, "asset", "12")  # 現金/預金

    journal_number = await _next_journal_number(db, company_id)

    header = JournalHeader(
        company_id=company_id,
        journal_number=journal_number,
        transaction_date=payment_date,
        voucher_type="payment",
        summary=f"経費支払: {report_title}",
        approval_status="draft",
        source_type="expense_payment",
        created_by=created_by,
    )
    db.add(header)
    await db.flush()

    # (借) 経費
    db.add(JournalLine(
        journal_header_id=header.journal_header_id,
        line_number=1,
        debit_credit="debit",
        account_id=expense_account.account_id,
        amount=total_amount,
        description=f"経費精算 {report_title}",
    ))
    # (貸) 現金
    db.add(JournalLine(
        journal_header_id=header.journal_header_id,
        line_number=2,
        debit_credit="credit",
        account_id=cash_account.account_id,
        amount=total_amount,
        description=f"経費支払 {report_title}",
    ))

    await db.flush()
    return header
