"""科目ごとの借方・貸方合計を、仕訳から直接集計する。

以前は転記（post）時に加算するだけの集計キャッシュ（`monthly_balances`）が
あり、月次残高・予実比較・帳簿検算がそれを読んでいた。取消（void）しても
減算されないため、同じ画面の試算表タブ（仕訳から集計）と数字が食い違った。

キャッシュに減算を足していくと、仕訳と同期し続けなければならない第二の真実が
増える。試算表と同じ条件で集計するこの関数に一本化して、キャッシュは消した。

除外条件は試算表（`reports.get_trial_balance`）と同一にすること。ここがずれると
同じ画面の2つのタブがまた食い違う。承認状態では絞らない（登録した仕訳は
未承認でも計上する）。
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import JournalHeader, JournalLine


async def account_totals_for_period(
    db: AsyncSession,
    company_id: UUID,
    start: date,
    end: date,
) -> dict[UUID, tuple[Decimal, Decimal]]:
    """期間内の有効な仕訳を科目ごとに集計する。

    Returns:
        科目ID -> (借方合計, 貸方合計)。行の無い科目は含まれない。
    """
    result = await db.execute(
        select(
            JournalLine.account_id,
            func.coalesce(
                func.sum(
                    case((JournalLine.debit_credit == "debit", JournalLine.amount), else_=Decimal("0"))
                ),
                0,
            ).label("debit_sum"),
            func.coalesce(
                func.sum(
                    case((JournalLine.debit_credit == "credit", JournalLine.amount), else_=Decimal("0"))
                ),
                0,
            ).label("credit_sum"),
        )
        .join(JournalHeader, JournalHeader.journal_header_id == JournalLine.journal_header_id)
        .where(
            JournalHeader.company_id == company_id,
            JournalHeader.transaction_date >= start,
            JournalHeader.transaction_date <= end,
            JournalHeader.is_deleted == False,  # noqa: E712
            JournalHeader.is_voided == False,  # noqa: E712
            JournalLine.is_deleted == False,  # noqa: E712
        )
        .group_by(JournalLine.account_id)
    )
    return {
        row.account_id: (Decimal(str(row.debit_sum)), Decimal(str(row.credit_sum)))
        for row in result.all()
    }
