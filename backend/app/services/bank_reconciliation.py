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
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
#
# 全銀協フォーマットの振込依頼人名は**半角カタカナ**で連携されるため、比較前にNFKC正規化して
# 全角カナへ寄せる（濁点の合成も行われる: "ｶ"+"ﾞ" → "ガ"）。したがって以下のトークンは
# NFKC後の表記（全角カナ・半角括弧）で列挙する。
#
# 法人格は全銀では括弧付きの略号で表される（前株 "ｶ)ﾀﾅｶ" / 後株 "ﾀﾅｶ(ｶ"）。
# 略号単体（"カ" 等）はごく普通の社名の一部になりうるため、**必ず括弧付きでのみ除去**する。
_LEGAL_ABBREVIATIONS = (
    "カ",      # 株式会社
    "ユ",      # 有限会社
    "ド",      # 合同会社
    "シ",      # 合資会社
    "メ",      # 合名会社
    "イ",      # 医療法人
    "ザイ",    # 財団法人
    "シヤ",    # 社団法人
    "ガク",    # 学校法人
    "シユウ",  # 宗教法人
    "トク",    # 特定非営利活動法人
    "ドク",    # 独立行政法人
    "ケン",    # 検査/研究法人等
    "キョウ",  # 協同組合等
    "ノウ",    # 農業協同組合
    "レン",    # 連合会
)
_NORMALIZE_TOKENS = (
    # 漢字表記の法人格
    "株式会社", "有限会社", "合同会社", "合資会社", "合名会社",
    "一般社団法人", "一般財団法人", "公益社団法人", "公益財団法人",
    "特定非営利活動法人", "独立行政法人", "医療法人", "学校法人", "宗教法人",
    "社会福祉法人", "社団法人", "財団法人", "農業協同組合", "協同組合",
    "(株)", "(有)", "(同)", "(資)", "(名)",
    # 全銀の括弧付き略号（前株・後株の双方）
    *(f"{a})" for a in _LEGAL_ABBREVIATIONS),
    *(f"({a}" for a in _LEGAL_ABBREVIATIONS),
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

    銀行から連携される振込依頼人名は全銀協フォーマットにより**半角カタカナ**である一方、
    取引先マスタは全角カナや漢字で登録されるため、そのまま比較すると別文字列として
    扱われ全く一致しない（"ﾀﾅｶｼｮｳｼﾞ" と "タナカショウジ" の類似度は0になる）。
    そこで最初にNFKC正規化を行い、半角カナ→全角カナ、濁点・半濁点の合成
    （"ｶ"+"ﾞ" → "ガ"）、全角英数→半角英数を揃えてから比較する。

    その後、法人格トークン・空白・記号を除去し大文字化する。
    """
    if not name:
        return ""
    # 半角カナ・全角英数・互換文字を正規形へ寄せる（比較の前提を揃える）。
    result = unicodedata.normalize("NFKC", name)
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

    date_score = (1.0 if date_diff == 0 else 0.0) if date_tolerance_days <= 0 else 1.0 - date_diff / date_tolerance_days

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
    # 全角数字・全角記号を半角へ寄せてから解釈する（銀行CSVには全角混じりがある）。
    cleaned = unicodedata.normalize("NFKC", raw or "")
    cleaned = cleaned.replace(",", "").replace("¥", "").strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return value if value != 0 else None


def decode_statement_bytes(content: bytes) -> str:
    """銀行明細ファイルのバイト列をテキストへ復号する。

    日本の銀行・カード会社のCSVは UTF-8 と Shift_JIS（cp932）が混在する。
    どちらでも読めない場合は理由を添えて ValueError を送出する
    （呼び出し側が 500 ではなく「読めない」という結果を返せるように）。
    """
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        "ファイルの文字コードを判定できませんでした（UTF-8 / Shift_JIS のいずれでも読めません）"
    )


# 和暦の元号 → 西暦への換算オフセット（元号の年数に足すと西暦になる）。
_ERA_OFFSETS = {"R": 2018, "令和": 2018, "H": 1988, "平成": 1988, "S": 1925, "昭和": 1925}
_ERA_DATE_RE = re.compile(
    r"^(R|H|S|令和|平成|昭和)\s*(\d{1,2})\s*[/年]\s*(\d{1,2})\s*[/月]\s*(\d{1,2})\s*日?$"
)
_DATE_FORMATS = ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%Y%m%d", "%Y年%m月%d日")


def _parse_date(raw: str) -> date | None:
    """銀行CSVの日付表記を解釈する。西暦の主要形式と和暦に対応する。"""
    text = unicodedata.normalize("NFKC", raw or "").strip()
    if not text:
        return None
    era = _ERA_DATE_RE.match(text)
    if era:
        try:
            return date(
                _ERA_OFFSETS[era.group(1)] + int(era.group(2)),
                int(era.group(3)),
                int(era.group(4)),
            )
        except ValueError:
            return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# 汎用取り込みの列対応（canonical名 → ヘッダ表記の候補）。
# 銀行ごとに列名が違うため候補を広く持ち、利用者が column_map で上書きできる。
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("取引日", "日付", "お取引日", "取引日付", "ご利用日", "利用日"),
    "deposit": ("入金額", "預入金額", "お預入額", "お預り金額", "預り金額", "入金"),
    "withdrawal": ("出金額", "引出金額", "お引出額", "お支払金額", "支払金額", "出金"),
    "amount": ("金額", "お取引金額", "入出金額", "取引金額", "ご利用金額"),
    "direction": ("入出金区分", "入出金", "区分", "種別"),
    "balance": ("残高", "差引残高", "お取引後残高", "取引後残高"),
    "description": ("摘要", "お取引内容", "内容", "メモ", "ご利用内容"),
    "counterparty": ("振込人名カナ", "振込人名", "お名前", "取引先", "振込依頼人名", "お支払先"),
}

# 入出金区分の値 → direction。NFKC正規化＋小文字化してから引く。
_DIRECTION_VALUES = {
    "入金": "deposit", "入": "deposit", "預入": "deposit", "お預り": "deposit",
    "deposit": "deposit", "credit": "deposit", "cr": "deposit", "+": "deposit",
    "出金": "withdrawal", "出": "withdrawal", "引出": "withdrawal", "お支払": "withdrawal",
    "withdrawal": "withdrawal", "debit": "withdrawal", "dr": "withdrawal", "-": "withdrawal",
}


@dataclass
class SkippedRow:
    """取り込めなかった行と、その理由。

    金額データを扱う以上「黙って捨てる」ことはしない。理由を呼び出し側へ返し、
    利用者がファイルの何行目を直せばよいか分かるようにする。
    """

    row_number: int  # ヘッダを1行目とした行番号
    reason: str


@dataclass
class BankCsvParseResult:
    rows: list[ParsedBankRow]
    skipped: list[SkippedRow]


def parse_bank_csv_detailed(
    csv_text: str,
    column_map: dict[str, str] | None = None,
) -> BankCsvParseResult:
    """銀行明細CSVをパースし、読めなかった行は理由つきで返す。

    column_map は canonical名（date/deposit/withdrawal/amount/direction/balance/
    description/counterparty）→ 実際のヘッダ名 の上書き。銀行・カード会社ごとの
    列名のばらつきを、利用者が自分のファイルに合わせて調整できるようにする。
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        return BankCsvParseResult(rows=[], skipped=[])

    headers = {(name or "").strip(): name for name in reader.fieldnames}

    def resolve(canonical: str) -> str | None:
        if column_map:
            override = (column_map.get(canonical) or "").strip()
            if override:
                return headers.get(override)
        for alias in _COLUMN_ALIASES[canonical]:
            if alias in headers:
                return headers[alias]
        return None

    columns = {name: resolve(name) for name in _COLUMN_ALIASES}

    def col(row: dict, canonical: str) -> str:
        field_name = columns[canonical]
        if field_name is None:
            return ""
        value = row.get(field_name)
        return value if value not in (None, "") else ""

    rows: list[ParsedBankRow] = []
    skipped: list[SkippedRow] = []

    for row_number, row in enumerate(reader, start=2):
        if all(value in (None, "") for value in row.values()):
            continue  # 末尾の空行など、データでない行は数えない

        txn_date = _parse_date(col(row, "date"))
        if txn_date is None:
            skipped.append(SkippedRow(row_number, f"日付「{col(row, 'date')}」を解釈できませんでした"))
            continue

        deposit = _parse_amount(col(row, "deposit")) if columns["deposit"] else None
        withdrawal = _parse_amount(col(row, "withdrawal")) if columns["withdrawal"] else None
        if deposit is not None and withdrawal is not None:
            skipped.append(SkippedRow(row_number, "入金額と出金額の両方に金額があり、方向を決められませんでした"))
            continue
        if deposit is not None:
            direction, amount = "deposit", abs(deposit)
        elif withdrawal is not None:
            direction, amount = "withdrawal", abs(withdrawal)
        else:
            # 金額が1列だけの形式（カード明細など）は、区分列か符号で方向を決める。
            single = _parse_amount(col(row, "amount")) if columns["amount"] else None
            if single is None:
                skipped.append(SkippedRow(row_number, "金額が読み取れませんでした"))
                continue
            direction_raw = unicodedata.normalize("NFKC", col(row, "direction")).strip().lower()
            direction = _DIRECTION_VALUES.get(direction_raw)
            if direction is None and not columns["direction"]:
                direction = "withdrawal" if single < 0 else None
            if direction is None:
                skipped.append(SkippedRow(row_number, "入出金の方向を決められませんでした"))
                continue
            amount = abs(single)

        rows.append(ParsedBankRow(
            transaction_date=txn_date,
            direction=direction,
            amount=amount,
            balance=_parse_amount(col(row, "balance")) if columns["balance"] else None,
            description=col(row, "description"),
            counterparty_name=col(row, "counterparty"),
        ))
    return BankCsvParseResult(rows=rows, skipped=skipped)


def parse_bank_csv(csv_text: str) -> list[ParsedBankRow]:
    """銀行明細CSVを取り込めた行だけ返す（後方互換用）。

    読めなかった行の理由が必要な場合は parse_bank_csv_detailed を使うこと。
    """
    return parse_bank_csv_detailed(csv_text).rows


# --- 非同期サービス（DB依存） ------------------------------------------------

async def import_statement_csv(
    db: AsyncSession,
    tenant_id: UUID,
    company_id: UUID,
    csv_text: str,
    column_map: dict[str, str] | None = None,
) -> list[BankStatementLine]:
    """銀行明細CSVを取り込んでBankStatementLineとして永続化する。"""
    lines, _skipped = await import_statement_detailed(db, tenant_id, company_id, csv_text, column_map)
    return lines


async def import_statement_detailed(
    db: AsyncSession,
    tenant_id: UUID,
    company_id: UUID,
    csv_text: str,
    column_map: dict[str, str] | None = None,
) -> tuple[list[BankStatementLine], list[SkippedRow]]:
    """銀行明細CSVを取り込み、読めなかった行の理由も一緒に返す。"""
    result = parse_bank_csv_detailed(csv_text, column_map)
    parsed = result.rows
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
    return lines, result.skipped


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
    now = datetime.now(UTC)
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
    line.reconciled_at = datetime.now(UTC)
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
