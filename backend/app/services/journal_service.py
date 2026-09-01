from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import JournalHeader, JournalLine, MonthlyBalance


class JournalService:
    """Business logic for journal operations."""

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
