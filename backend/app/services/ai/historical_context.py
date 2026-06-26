import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Account, JournalHeader, JournalLine, SubAccount

logger = logging.getLogger(__name__)


class HistoricalContextProvider:
    """過去仕訳データを取得し、AI推論のコンテキストとして提供する。"""

    @staticmethod
    async def get_similar_journals(
        db: AsyncSession,
        company_id: UUID,
        description: str,
        amount: float,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """類似する過去仕訳を取得する。

        検索基準:
        - 摘要にキーワードが含まれる仕訳を優先
        - 金額が近い仕訳を優先
        - 直近の仕訳を優先
        """
        keywords = [w for w in description.split() if len(w) >= 2]
        if not keywords:
            keywords = [description]

        result = await db.execute(
            select(JournalHeader).where(
                JournalHeader.company_id == company_id,
                JournalHeader.is_deleted == False,  # noqa: E712
                JournalHeader.is_voided == False,  # noqa: E712
                JournalHeader.approval_status == "posted",
            ).order_by(
                JournalHeader.transaction_date.desc()
            ).limit(500)
        )
        all_journals = result.scalars().all()

        scored: list[tuple[float, JournalHeader]] = []
        for journal in all_journals:
            score = 0.0
            if journal.summary:
                for kw in keywords:
                    if kw in journal.summary:
                        score += 10.0

            lines_result = await db.execute(
                select(JournalLine).where(
                    JournalLine.journal_header_id == journal.journal_header_id,
                    JournalLine.is_deleted == False,  # noqa: E712
                )
            )
            lines = lines_result.scalars().all()

            for line in lines:
                amount_diff = abs(float(line.amount) - amount)
                if amount_diff == 0:
                    score += 5.0
                elif amount_diff < amount * 0.1:
                    score += 3.0
                elif amount_diff < amount * 0.3:
                    score += 1.0

            days_ago = (date.today() - journal.transaction_date).days
            score += max(0, 5 - days_ago / 30)

            if score > 0:
                scored.append((score, journal))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_journals = [j for _, j in scored[:limit]]

        return await HistoricalContextProvider._format_journals(db, top_journals)

    @staticmethod
    async def get_account_patterns(
        db: AsyncSession,
        company_id: UUID,
        description_keywords: list[str],
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """特定のキーワードに関連する勘定科目の使用パターンを取得する。"""
        result = await db.execute(
            select(JournalHeader, JournalLine, Account).join(JournalLine).join(Account).where(
                JournalHeader.company_id == company_id,
                JournalHeader.is_deleted == False,  # noqa: E712
                JournalHeader.is_voided == False,  # noqa: E712
                JournalHeader.approval_status == "posted",
            ).order_by(JournalHeader.transaction_date.desc()).limit(1000)
        )
        rows = result.all()

        patterns: dict[str, dict[str, Any]] = {}
        for header, line, account in rows:
            if not header.summary:
                continue
            matched = any(kw in header.summary for kw in description_keywords)
            if not matched:
                continue

            key = f"{account.account_code}:{line.debit_credit}"
            if key not in patterns:
                patterns[key] = {
                    "account_code": account.account_code,
                    "account_name": account.account_name,
                    "debit_credit": line.debit_credit,
                    "count": 0,
                    "avg_amount": 0.0,
                    "total_amount": 0.0,
                    "sample_summaries": [],
                }
            patterns[key]["count"] += 1
            patterns[key]["total_amount"] += float(line.amount)
            if len(patterns[key]["sample_summaries"]) < 3:
                patterns[key]["sample_summaries"].append(header.summary)

        for p in patterns.values():
            p["avg_amount"] = p["total_amount"] / p["count"] if p["count"] > 0 else 0

        sorted_patterns = sorted(patterns.values(), key=lambda x: x["count"], reverse=True)
        return sorted_patterns[:limit]

    @staticmethod
    async def get_frequent_account_combos(
        db: AsyncSession,
        company_id: UUID,
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        """頻繁に使用される借方・貸方の科目組み合わせを取得する。"""
        result = await db.execute(
            select(JournalHeader).where(
                JournalHeader.company_id == company_id,
                JournalHeader.is_deleted == False,  # noqa: E712
                JournalHeader.is_voided == False,  # noqa: E712
                JournalHeader.approval_status == "posted",
            ).order_by(JournalHeader.transaction_date.desc()).limit(2000)
        )
        journals = result.scalars().all()

        combos: dict[str, dict[str, Any]] = {}
        for journal in journals:
            lines_result = await db.execute(
                select(JournalLine, Account).join(Account).where(
                    JournalLine.journal_header_id == journal.journal_header_id,
                    JournalLine.is_deleted == False,  # noqa: E712
                )
            )
            lines = lines_result.all()

            debit_accounts = [(a.account_code, a.account_name) for _, a in lines if _.debit_credit == "debit"]
            credit_accounts = [(a.account_code, a.account_name) for _, a in lines if _.debit_credit == "credit"]

            for d_code, d_name in debit_accounts:
                for c_code, c_name in credit_accounts:
                    key = f"{d_code}->{c_code}"
                    if key not in combos:
                        combos[key] = {
                            "debit_account_code": d_code,
                            "debit_account_name": d_name,
                            "credit_account_code": c_code,
                            "credit_account_name": c_name,
                            "count": 0,
                            "sample_summaries": [],
                        }
                    combos[key]["count"] += 1
                    if journal.summary and len(combos[key]["sample_summaries"]) < 3:
                        combos[key]["sample_summaries"].append(journal.summary)

        sorted_combos = sorted(combos.values(), key=lambda x: x["count"], reverse=True)
        return sorted_combos[:limit]

    @staticmethod
    async def _format_journals(
        db: AsyncSession,
        journals: list[JournalHeader],
    ) -> list[dict[str, Any]]:
        """仕訳をAIコンテキスト用の形式にフォーマットする。"""
        formatted: list[dict[str, Any]] = []

        for journal in journals:
            lines_result = await db.execute(
                select(JournalLine, Account).join(Account).where(
                    JournalLine.journal_header_id == journal.journal_header_id,
                    JournalLine.is_deleted == False,  # noqa: E712
                ).order_by(JournalLine.line_number)
            )
            rows = lines_result.all()

            lines_data: list[dict[str, Any]] = []
            for line, account in rows:
                sub_account_name = None
                if line.sub_account_id:
                    sa_result = await db.execute(
                        select(SubAccount).where(SubAccount.sub_account_id == line.sub_account_id)
                    )
                    sub = sa_result.scalar_one_or_none()
                    sub_account_name = sub.sub_account_name if sub else None

                lines_data.append({
                    "debit_credit": line.debit_credit,
                    "account_code": account.account_code,
                    "account_name": account.account_name,
                    "sub_account_name": sub_account_name,
                    "amount": float(line.amount),
                    "tax_amount": float(line.tax_amount),
                    "description": line.description,
                })

            formatted.append({
                "transaction_date": journal.transaction_date.isoformat(),
                "journal_number": journal.journal_number,
                "summary": journal.summary,
                "voucher_type": journal.voucher_type,
                "lines": lines_data,
            })

        return formatted

    @staticmethod
    async def build_context(
        db: AsyncSession,
        company_id: UUID,
        description: str,
        amount: float,
    ) -> dict[str, Any]:
        """AI推論用の完全なコンテキストを構築する。"""
        similar = await HistoricalContextProvider.get_similar_journals(
            db, company_id, description, amount, limit=5
        )

        keywords = [w for w in description.split() if len(w) >= 2] or [description]
        patterns = await HistoricalContextProvider.get_account_patterns(
            db, company_id, keywords, limit=10
        )

        frequent_combos = await HistoricalContextProvider.get_frequent_account_combos(
            db, company_id, limit=10
        )

        return {
            "similar_journals": similar,
            "account_patterns": patterns,
            "frequent_combinations": frequent_combos,
            "company_id": str(company_id),
            "description": description,
            "amount": amount,
        }
