"""銀行明細取込・自動消込サービス（フェーズ4）。

銀行明細CSVを取り込み、未消込の仕訳明細（銀行勘定）に対して金額一致・日付近接・
振込人名類似度でスコアリングして自動消込する。

突合の中核（正規化・類似度・スコアリング・最良候補選択）はDB非依存の純粋関数として
切り出し、単体テスト可能にしている。
"""
import csv
import io
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import BankStatementLine, JournalHeader, JournalLine

logger = logging.getLogger(__name__)

DEFAULT_DATE_TOLERANCE_DAYS = 3
DEFAULT_MIN_SCORE = 0.6
DEFAULT_NAME_WEIGHT = 0.4
# 振込手数料の許容差（この額まで金額差を許して消込を成立させる）。
DEFAULT_MAX_FEE = Decimal("0")

# 名称正規化で除去する法人格・振込種別トークン。
_NORMALIZE_TOKENS = (
    "株式会社", "有限会社", "合同会社", "合資会社", "合名会社",
    "カ)", "カ）", "(カ", "（カ", "ｶ)", "ｶ）",
    "(株)", "（株）", "(有)", "（有）",
)
_NORMALIZE_STRIP = re.compile(r"[\s　・,.，。()（）\-ー]")


# --- 純粋関数（DB非依存・テスト可能） ---------------------------------------

@dataclass
class ReconciliationCandidate:
    """消込候補（未消込の仕訳明細等を正規化したもの）。"""
    ref_id: str
    amount: Decimal
    date: date
    counterparty_name: str = ""


@dataclass
class ParsedBankRow:
    """銀行CSVの1行をパースした結果。"""
    transaction_date: date
    direction: str  # "deposit" | "withdrawal"
    amount: Decimal
    balance: Decimal | None
    description: str
    counterparty_name: str


def normalize_name(name: str | None) -> str:
    """振込人名・摘要を突合用に正規化する。

    法人格トークン・空白・記号を除去し大文字化する。
    """
    if not name:
        return ""
    result = name
    for token in _NORMALIZE_TOKENS:
        result = result.replace(token, "")
    result = _NORMALIZE_STRIP.sub("", result)
    return result.upper()


def name_similarity(a: str | None, b: str | None) -> float:
    """2つの名称の類似度を0.0〜1.0で返す（正規化後の比較）。"""
    na, nb = normalize_name(a), normalize_name(b)
    if not na and not nb:
        return 0.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def match_score(
    amount: Decimal,
    txn_date: date,
    counterparty_name: str,
    candidate: ReconciliationCandidate,
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
    name_weight: float = DEFAULT_NAME_WEIGHT,
    amount_tolerance: Decimal = DEFAULT_MAX_FEE,
) -> float | None:
    """銀行明細と候補の突合スコアを返す。一致不能ならNone。

    - 金額差がamount_tolerance（振込手数料相当）を超えたらNone。完全一致は満点、
      手数料差のある一致は軽くペナルティを与え、完全一致が優先されるようにする。
    - 日付差が許容日数を超えたらNone。
    - スコア = (1-name_weight)*日付近接スコア + name_weight*名称類似度。
    """
    amount_diff = abs(Decimal(amount) - Decimal(candidate.amount))
    if amount_diff > Decimal(amount_tolerance):
        return None

    date_diff = abs((txn_date - candidate.date).days)
    if date_diff > date_tolerance_days:
        return None

    if date_tolerance_days <= 0:
        date_score = 1.0 if date_diff == 0 else 0.0
    else:
        date_score = 1.0 - (date_diff / date_tolerance_days)

    name_score = name_similarity(counterparty_name, candidate.counterparty_name)
    score = (1.0 - name_weight) * date_score + name_weight * name_score
    if amount_diff > 0 and Decimal(amount_tolerance) > 0:
        # 手数料差のある一致は最大50%減点し、完全一致を優先する。
        score *= 1.0 - 0.5 * (float(amount_diff) / float(amount_tolerance))
    return score


def find_best_match(
    amount: Decimal,
    txn_date: date,
    counterparty_name: str,
    candidates: list[ReconciliationCandidate],
    min_score: float = DEFAULT_MIN_SCORE,
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
    name_weight: float = DEFAULT_NAME_WEIGHT,
    amount_tolerance: Decimal = DEFAULT_MAX_FEE,
) -> tuple[ReconciliationCandidate, float] | None:
    """最良の候補と、そのスコアを返す。min_score未満しかなければNone。

    同点時は日付が近い候補を優先する。
    """
    best: tuple[ReconciliationCandidate, float, int] | None = None
    for cand in candidates:
        score = match_score(
            amount, txn_date, counterparty_name, cand, date_tolerance_days, name_weight,
            amount_tolerance,
        )
        if score is None or score < min_score:
            continue
        date_diff = abs((txn_date - cand.date).days)
        if best is None or score > best[1] or (score == best[1] and date_diff < best[2]):
            best = (cand, score, date_diff)
    if best is None:
        return None
    return best[0], best[1]


def _parse_amount(raw: str) -> Decimal | None:
    cleaned = (raw or "").replace(",", "").replace("¥", "").replace("￥", "").strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return value if value != 0 else None


def parse_bank_csv(csv_text: str) -> list[ParsedBankRow]:
    """汎用銀行明細CSVをパースする。

    想定列（表記ゆれ許容）: 取引日/日付, 入金額/預入金額, 出金額/引出金額,
    残高, 摘要/お取引内容, 振込人名/振込人名カナ/お名前
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    rows: list[ParsedBankRow] = []

    def col(row: dict, *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return value
        return ""

    for row in reader:
        try:
            date_raw = col(row, "取引日", "日付", "お取引日")
            txn_date = datetime.strptime(date_raw, "%Y/%m/%d").date()
        except ValueError:
            logger.warning("Skipping bank CSV row with bad date: %s", row)
            continue

        deposit = _parse_amount(col(row, "入金額", "預入金額", "お預入額"))
        withdrawal = _parse_amount(col(row, "出金額", "引出金額", "お引出額"))
        if deposit is not None:
            direction, amount = "deposit", abs(deposit)
        elif withdrawal is not None:
            direction, amount = "withdrawal", abs(withdrawal)
        else:
            continue

        rows.append(ParsedBankRow(
            transaction_date=txn_date,
            direction=direction,
            amount=amount,
            balance=_parse_amount(col(row, "残高", "差引残高")),
            description=col(row, "摘要", "お取引内容", "内容"),
            counterparty_name=col(row, "振込人名カナ", "振込人名", "お名前", "取引先"),
        ))
    return rows


# --- 非同期サービス（DB依存） ------------------------------------------------

async def import_statement_csv(
    db: AsyncSession,
    tenant_id: UUID,
    company_id: UUID,
    csv_text: str,
) -> list[BankStatementLine]:
    """銀行明細CSVを取り込んでBankStatementLineとして永続化する。"""
    parsed = parse_bank_csv(csv_text)
    lines: list[BankStatementLine] = []
    for row in parsed:
        line = BankStatementLine(
            tenant_id=tenant_id,
            company_id=company_id,
            transaction_date=row.transaction_date,
            direction=row.direction,
            amount=row.amount,
            balance=row.balance,
            description=row.description or None,
            counterparty_name=row.counterparty_name or None,
            source="csv",
        )
        db.add(line)
        lines.append(line)
    if lines:
        await db.commit()
        for line in lines:
            await db.refresh(line)
    return lines


async def list_statement_lines(
    db: AsyncSession,
    company_id: UUID,
    reconciled: bool | None = None,
    limit: int = 100,
) -> list[BankStatementLine]:
    """銀行明細を一覧取得する。"""
    conditions = [BankStatementLine.company_id == company_id]
    if reconciled is not None:
        conditions.append(BankStatementLine.is_reconciled == reconciled)  # noqa: E712
    result = await db.execute(
        select(BankStatementLine)
        .where(*conditions)
        .order_by(BankStatementLine.transaction_date.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _load_candidates(
    db: AsyncSession, company_id: UUID, bank_account_id: UUID
) -> list[tuple[ReconciliationCandidate, JournalLine]]:
    """銀行勘定に付いた未消込の仕訳明細を消込候補として読み込む。"""
    already = await db.execute(
        select(BankStatementLine.reconciled_journal_line_id).where(
            BankStatementLine.company_id == company_id,
            BankStatementLine.reconciled_journal_line_id.isnot(None),
        )
    )
    reconciled_ids = {r for (r,) in already.all()}

    result = await db.execute(
        select(JournalLine, JournalHeader)
        .join(JournalHeader, JournalLine.journal_header_id == JournalHeader.journal_header_id)
        .where(
            JournalHeader.company_id == company_id,
            JournalLine.account_id == bank_account_id,
            JournalLine.is_deleted == False,  # noqa: E712
            JournalHeader.is_deleted == False,  # noqa: E712
            JournalHeader.is_voided == False,  # noqa: E712
        )
    )
    candidates: list[tuple[ReconciliationCandidate, JournalLine]] = []
    for line, header in result.all():
        if line.journal_line_id in reconciled_ids:
            continue
        candidates.append((
            ReconciliationCandidate(
                ref_id=str(line.journal_line_id),
                amount=line.amount,
                date=header.transaction_date,
                counterparty_name=line.description or header.summary or "",
            ),
            line,
        ))
    return candidates


async def auto_reconcile(
    db: AsyncSession,
    company_id: UUID,
    bank_account_id: UUID,
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
    min_score: float = DEFAULT_MIN_SCORE,
    max_fee: Decimal = DEFAULT_MAX_FEE,
) -> dict:
    """未消込の銀行明細を仕訳明細に対して自動消込する。

    金額一致を必須に、日付近接と名称類似度でスコアリングし、候補は1対1で割り当てる。
    """
    bank_lines = await list_statement_lines(db, company_id, reconciled=False, limit=1000)
    candidates = await _load_candidates(db, company_id, bank_account_id)

    pool = {c.ref_id: (c, line) for c, line in candidates}
    now = datetime.now(timezone.utc)
    matched = 0

    for bank_line in bank_lines:
        available = [c for c, _ in pool.values()]
        best = find_best_match(
            bank_line.amount,
            bank_line.transaction_date,
            bank_line.counterparty_name or "",
            available,
            min_score=min_score,
            date_tolerance_days=date_tolerance_days,
            amount_tolerance=max_fee,
        )
        if best is None:
            continue
        cand, _score = best
        _, journal_line = pool.pop(cand.ref_id)
        bank_line.is_reconciled = True
        bank_line.reconciled_journal_line_id = journal_line.journal_line_id
        bank_line.reconciled_at = now
        matched += 1

    if matched:
        await db.commit()

    return {
        "total_unreconciled": len(bank_lines),
        "matched": matched,
        "unmatched": len(bank_lines) - matched,
    }


async def manual_match(
    db: AsyncSession,
    company_id: UUID,
    bank_statement_line_id: UUID,
    journal_line_id: UUID,
) -> BankStatementLine | None:
    """銀行明細を仕訳明細に手動で消込する。"""
    result = await db.execute(
        select(BankStatementLine).where(
            BankStatementLine.bank_statement_line_id == bank_statement_line_id,
            BankStatementLine.company_id == company_id,
        )
    )
    line = result.scalar_one_or_none()
    if line is None:
        return None
    line.is_reconciled = True
    line.reconciled_journal_line_id = journal_line_id
    line.reconciled_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(line)
    return line


async def unmatch(
    db: AsyncSession,
    company_id: UUID,
    bank_statement_line_id: UUID,
) -> BankStatementLine | None:
    """銀行明細の消込を解除する。"""
    result = await db.execute(
        select(BankStatementLine).where(
            BankStatementLine.bank_statement_line_id == bank_statement_line_id,
            BankStatementLine.company_id == company_id,
        )
    )
    line = result.scalar_one_or_none()
    if line is None:
        return None
    line.is_reconciled = False
    line.reconciled_journal_line_id = None
    line.reconciled_at = None
    await db.commit()
    await db.refresh(line)
    return line
