"""銀行明細から仕訳ドラフトを起こすサービス。

kAIkei の中核フロー「銀行データ → 仕訳変換」の変換部分。

これまで銀行明細は、他の経路で作られた仕訳への「消込」にしか使えなかった。
しかし実際の作業では、銀行明細こそが仕訳の発生源である（明細を取り込む →
相手科目を決めて仕訳にする → 確定する）。ここでは未消込の明細1件について:

- 学習器（`journal_learning`）が過去の確定仕訳から相手科目の候補を出す。
- 人が候補を確認・修正してドラフトを作成する。作成された仕訳が確定（posted）
  されれば、それ自体が次の学習データになる（修正が学習に返る）。

候補の出し方の方針（会計では自信のない推測を自動で流すのが最も悪い）:

- 相手科目が1つに定まらない候補（複合仕訳の形）は自動仕訳化の対象にしない。
- 学習器が `reliable` とし、かつ候補の中に銀行科目が正しい側で含まれている
  場合だけ `reliable` とする。それ以外は「人が選ぶための候補」として返す。
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Account, BankStatementLine, JournalHeader, JournalLine
from app.services.auto_journal import _add_balanced
from app.services.journal_learning import suggest_from_history
from app.services.journal_numbering import insert_with_number


class AlreadyReconciledError(ValueError):
    """消込済みの明細を再度仕訳化しようとした。"""


async def _get_account(db: AsyncSession, company_id: UUID, account_id: UUID) -> Account | None:
    result = await db.execute(
        select(Account).where(
            Account.account_id == account_id,
            Account.company_id == company_id,
            Account.is_active.is_(True),
            Account.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def _get_line(db: AsyncSession, company_id: UUID, line_id: UUID) -> BankStatementLine | None:
    result = await db.execute(
        select(BankStatementLine).where(
            BankStatementLine.bank_statement_line_id == line_id,
            BankStatementLine.company_id == company_id,
        )
    )
    return result.scalar_one_or_none()


async def suggest_for_bank_line(
    db: AsyncSession,
    company_id: UUID,
    line_id: UUID,
    bank_account_id: UUID,
) -> dict:
    """未消込の銀行明細について、相手科目の候補を学習器から返す。"""
    line = await _get_line(db, company_id, line_id)
    if line is None:
        raise LookupError("銀行明細が見つかりません")
    if line.is_reconciled:
        raise AlreadyReconciledError("この明細は既に消込済みです")
    bank_account = await _get_account(db, company_id, bank_account_id)
    if bank_account is None:
        raise ValueError("銀行の勘定科目が見つかりません（自社の有効な科目を指定してください）")

    base = await suggest_from_history(
        db,
        company_id,
        description=line.description or "",
        amount=line.amount,
        partner_name=line.counterparty_name,
    )

    candidates: list[dict] = []
    for candidate in base["candidates"]:
        if line.direction == "deposit":
            # 入金: 借方が銀行科目、相手は貸方。
            counterparts = candidate["credit_accounts"]
            bank_side = candidate["debit_accounts"]
        else:
            # 出金: 貸方が銀行科目、相手は借方。
            counterparts = candidate["debit_accounts"]
            bank_side = candidate["credit_accounts"]
        if len(counterparts) != 1:
            continue  # 相手が1科目に定まらない候補は、1明細→1仕訳の形にできない
        counterpart = counterparts[0]
        if counterpart["account_id"] == str(bank_account_id):
            continue
        matches_bank = any(a["account_code"] == bank_account.account_code for a in bank_side)
        candidates.append(
            {
                "account_id": counterpart["account_id"],
                "account_code": counterpart["account_code"],
                "account_name": counterpart["account_name"],
                "confidence": candidate["confidence"],
                "support": candidate["support"],
                "exact_matches": candidate["exact_matches"],
                "reliable": bool(candidate["reliable"] and matches_bank),
                "matches_bank_account": matches_bank,
            }
        )

    return {
        "status": base["status"],
        "trained_examples": base["trained_examples"],
        "direction": line.direction,
        "bank_account_id": str(bank_account.account_id),
        "bank_account_code": bank_account.account_code,
        "bank_account_name": bank_account.account_name,
        "candidates": candidates,
    }


async def create_journal_from_bank_line(
    db: AsyncSession,
    *,
    company_id: UUID,
    line_id: UUID,
    bank_account_id: UUID,
    counterpart_account_id: UUID,
    created_by: UUID,
) -> JournalHeader:
    """銀行明細1件から2行の仕訳ドラフトを作り、明細をその仕訳へ消し込む。

    相手科目は人が確定した値をそのまま使う（候補の提示は suggest_for_bank_line
    の役割で、ここでは推測しない）。作られた仕訳は下書きであり、確定（posted）
    されると学習器の学習データになる。
    """
    line = await _get_line(db, company_id, line_id)
    if line is None:
        raise LookupError("銀行明細が見つかりません")
    if line.is_reconciled:
        raise AlreadyReconciledError("この明細は既に消込済みです")
    if bank_account_id == counterpart_account_id:
        raise ValueError("銀行の科目と相手科目に同じ科目は指定できません")
    bank_account = await _get_account(db, company_id, bank_account_id)
    if bank_account is None:
        raise ValueError("銀行の勘定科目が見つかりません（自社の有効な科目を指定してください）")
    counterpart = await _get_account(db, company_id, counterpart_account_id)
    if counterpart is None:
        raise ValueError("相手の勘定科目が見つかりません（自社の有効な科目を指定してください）")

    summary = line.description or line.counterparty_name or "銀行明細"
    is_deposit = line.direction == "deposit"

    header = await insert_with_number(
        db,
        company_id,
        lambda number: JournalHeader(
            company_id=company_id,
            journal_number=number,
            transaction_date=line.transaction_date,
            voucher_type="receipt" if is_deposit else "payment",
            summary=summary,
            approval_status="draft",
            source_type="bank_statement",
            created_by=created_by,
        ),
    )

    bank_jl = JournalLine(
        journal_header_id=header.journal_header_id,
        line_number=1 if is_deposit else 2,
        debit_credit="debit" if is_deposit else "credit",
        account_id=bank_account.account_id,
        amount=line.amount,
        description=summary,
    )
    counterpart_jl = JournalLine(
        journal_header_id=header.journal_header_id,
        line_number=2 if is_deposit else 1,
        debit_credit="credit" if is_deposit else "debit",
        account_id=counterpart.account_id,
        amount=line.amount,
        description=summary,
    )
    _add_balanced(db, [bank_jl, counterpart_jl], f"銀行明細 {line.transaction_date} {line.amount}")
    await db.flush()  # 仕訳明細のIDを確定させてから消込先に参照させる

    line.is_reconciled = True
    line.reconciled_journal_line_id = bank_jl.journal_line_id
    line.reconciled_at = datetime.now(UTC)
    await db.commit()

    result = await db.execute(
        select(JournalHeader)
        .options(selectinload(JournalHeader.lines))
        .where(JournalHeader.journal_header_id == header.journal_header_id)
    )
    return result.scalar_one()
