from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import JournalHeader, JournalLine, MonthlyBalance
from app.services.validation_engine import ValidationError, ValidationEngine


class JournalService:
    """Business logic for journal operations."""

    @staticmethod
    async def approve_journal(
        db: AsyncSession,
        journal_header_id: UUID,
        approver_id: UUID,
    ) -> JournalHeader:
        """Approve a journal entry (transition from draft/waiting to approved)."""
        result = await db.execute(
            select(JournalHeader).where(
                JournalHeader.journal_header_id == journal_header_id,
                JournalHeader.is_deleted == False,  # noqa: E712
            )
        )
        journal = result.scalar_one_or_none()
        if not journal:
            raise ValueError("Journal not found")

        if journal.approval_status not in ("draft", "waiting"):
            raise ValueError(f"Cannot approve journal in status: {journal.approval_status}")

        if journal.created_by == approver_id:
            raise ValidationError(
                code="SOD-001",
                message="Segregation of Duties violation: creator cannot approve their own journal",
            )

        journal.approval_status = "approved"
        journal.approved_by = approver_id
        await db.flush()
        await db.refresh(journal)
        return journal

    @staticmethod
    async def post_journal(db: AsyncSession, journal_header_id: UUID) -> JournalHeader:
        """Post an approved journal (transition to posted status and update balances)."""
        result = await db.execute(
            select(JournalHeader).where(
                JournalHeader.journal_header_id == journal_header_id,
                JournalHeader.is_deleted == False,  # noqa: E712
            )
        )
        journal = result.scalar_one_or_none()
        if not journal:
            raise ValueError("Journal not found")

        if journal.approval_status != "approved":
            raise ValueError("Only approved journals can be posted")

        journal.approval_status = "posted"
        await db.flush()

        await JournalService._update_monthly_balance(db, journal)
        await db.refresh(journal)
        return journal

    @staticmethod
    async def _update_monthly_balance(db: AsyncSession, journal: JournalHeader) -> None:
        """Update monthly balances after posting a journal."""
        year = journal.transaction_date.year
        month = journal.transaction_date.month

        lines_result = await db.execute(
            select(JournalLine).where(
                JournalLine.journal_header_id == journal.journal_header_id,
                JournalLine.is_deleted == False,  # noqa: E712
            )
        )
        lines = lines_result.scalars().all()

        for line in lines:
            balance_result = await db.execute(
                select(MonthlyBalance).where(
                    MonthlyBalance.company_id == journal.company_id,
                    MonthlyBalance.account_id == line.account_id,
                    MonthlyBalance.year == year,
                    MonthlyBalance.month == month,
                )
            )
            balance = balance_result.scalar_one_or_none()

            if not balance:
                balance = MonthlyBalance(
                    company_id=journal.company_id,
                    account_id=line.account_id,
                    year=year,
                    month=month,
                    debit_total=Decimal("0"),
                    credit_total=Decimal("0"),
                )
                db.add(balance)

            if line.debit_credit == "debit":
                balance.debit_total += line.amount
            else:
                balance.credit_total += line.amount

        await db.flush()
