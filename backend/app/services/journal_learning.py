"""自動仕訳学習: 過去の確定仕訳から学び、新しい取引への仕訳候補を提示する。

kAIkei の製品軸である「自動仕訳学習」の中核。既存の仕組みとの違い:

- `auto_journal.py` は請求書・給与など発生源が決まった仕訳を**ルールで**生成する。
- `services/ai/` の推論は外部 LLM に過去仕訳を文脈として渡す。プロバイダ未設定では
  動かず、結果も確率的で再現性がない。
- ここは**自社の確定済み仕訳だけ**を学習データにする統計的な学習器で、
  外部送信も LLM も使わない。学習も推論もこのプロセスの中（利用者の環境）で
  完結し、同じ入力には必ず同じ候補を返す（決定的）。

学習の単位は「借方科目の組み合わせ × 貸方科目の組み合わせ」（コンボ）。
特徴は摘要・明細説明のテキスト（単語と文字バイグラム。日本語は分かち書き
されないため、形態素解析に依存しないバイグラムを併用する）と金額の桁帯。
数字列（請求書番号・日付など）はノイズになるため正規化で潰す。

控えめさの設計（会計では「自信のない推測を自信ありげに出す」のが最も悪い）:

- 学習データが `MIN_EXAMPLES` 件未満なら候補を出さない（`insufficient_data`）。
- 過去と特徴が一切重ならない取引には候補を出さない（`no_matching_history`）。
- 支持の薄いコンボは候補から落とし、残った候補にも `reliable`（信頼できる
  水準か）を必ず付ける。呼び出し側は `reliable` でない候補を自動入力に
  使ってはならない。
"""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Account, JournalHeader, JournalLine

# 摘要が完全一致（数字を潰した正規形で）した場合の重み。特徴の重なりより
# 強く効かせる: 「毎月の家賃」のような繰り返し取引が学習の主対象のため。
EXACT_PATTERN_WEIGHT = 10

# 金額の桁帯は弱い特徴なので、テキスト特徴より重みを落とす。
AMOUNT_FEATURE_WEIGHT = 0.5

_DIGITS = re.compile(r"\d+")
_SEPARATORS = re.compile(r"[\s　、。,．・/／\\|｜:：;；()（）\[\]［］「」『』\"'’“”]+")


def normalize_text(text: str) -> str:
    """テキストを比較可能な正規形にする。

    全角/半角を揃え（NFKC）、英字を小文字化し、数字列を `#` に潰し、
    区切り文字を単一スペースにする。請求書番号や日付の違いで
    「別の取引」に分かれてしまうのを防ぐのが数字マスクの目的。
    """
    normalized = unicodedata.normalize("NFKC", text or "").lower()
    normalized = _DIGITS.sub("#", normalized)
    normalized = _SEPARATORS.sub(" ", normalized)
    return normalized.strip()


def pattern_key(text: str) -> str:
    """完全一致判定用のキー（正規化した全文）。"""
    return normalize_text(text)


def extract_features(text: str, amount: Decimal | None = None) -> set[str]:
    """テキストと金額から特徴集合を作る。

    - `w:<単語>`: スペースで区切られた単語（2文字以上）
    - `g:<2文字>`: 空白を除いた文字列の文字バイグラム（日本語向け）
    - `amt:<桁>`: 金額の桁帯（10の何乗か）。弱い特徴として別枠で数える
    """
    normalized = normalize_text(text)
    features: set[str] = set()

    for word in normalized.split(" "):
        if len(word) >= 2:
            features.add(f"w:{word}")

    compact = normalized.replace(" ", "")
    for i in range(len(compact) - 1):
        features.add(f"g:{compact[i:i + 2]}")

    if amount is not None and amount > 0:
        bucket = int(math.floor(math.log10(float(amount))))
        features.add(f"amt:{bucket}")

    return features


# 仕訳の組み合わせ（借方科目コード列 × 貸方科目コード列）。
Combo = tuple[tuple[str, ...], tuple[str, ...]]


@dataclass(frozen=True)
class JournalExample:
    """学習データ1件（確定済み仕訳1件分）。"""

    text: str  # 摘要 + 明細説明を連結したもの
    amount: Decimal  # 代表金額（借方合計）
    debit_codes: tuple[str, ...]
    credit_codes: tuple[str, ...]

    @property
    def combo(self) -> Combo:
        return (self.debit_codes, self.credit_codes)


@dataclass
class JournalCandidate:
    """仕訳候補1件。"""

    debit_codes: tuple[str, ...]
    credit_codes: tuple[str, ...]
    confidence: float  # 0..1。全候補のスコアに対する首位の割合
    support: int  # この候補に寄与した学習データの件数
    exact_matches: int  # 摘要が完全一致した件数
    reliable: bool  # 自動入力に使ってよい水準か
    matched_features: list[str] = field(default_factory=list)  # 根拠（単語特徴のみ）


@dataclass
class SuggestionResult:
    status: str  # "ok" | "insufficient_data" | "no_matching_history"
    trained_examples: int
    candidates: list[JournalCandidate] = field(default_factory=list)


class JournalPatternLearner:
    """確定仕訳の蓄積から仕訳候補を学習する、決定的な統計学習器。"""

    # これ未満の学習データでは候補を出さない。数件の偶然を「学習した」と
    # 言わないための下限。
    MIN_EXAMPLES = 5
    # 候補として残す最小の支持件数。ただし摘要の完全一致があれば1件でも残す
    # （繰り返し取引の初回再現は、それ自体が強い根拠になるため）。
    MIN_SUPPORT = 2
    # `reliable` とみなす信頼度の下限。
    RELIABLE_CONFIDENCE = 0.6

    def __init__(self) -> None:
        self._examples: list[JournalExample] = []
        self._example_features: list[set[str]] = []
        self._example_keys: list[str] = []

    # -- 学習 ---------------------------------------------------------------

    def add_example(self, example: JournalExample) -> None:
        self._examples.append(example)
        self._example_features.append(extract_features(example.text, example.amount))
        self._example_keys.append(pattern_key(example.text))

    def train(self, examples: list[JournalExample]) -> None:
        for example in examples:
            self.add_example(example)

    @property
    def example_count(self) -> int:
        return len(self._examples)

    # -- 推論 ---------------------------------------------------------------

    def suggest(
        self,
        *,
        text: str,
        amount: Decimal | None = None,
        limit: int = 3,
    ) -> SuggestionResult:
        """新しい取引テキストに対する仕訳候補を返す。"""
        if self.example_count < self.MIN_EXAMPLES:
            return SuggestionResult(status="insufficient_data", trained_examples=self.example_count)

        query_features = extract_features(text, amount)
        query_key = pattern_key(text)

        scores: Counter[Combo] = Counter()
        supports: Counter[Combo] = Counter()
        exacts: Counter[Combo] = Counter()
        matched_words: dict[Combo, set[str]] = {}

        for example, features, key in zip(
            self._examples, self._example_features, self._example_keys, strict=True
        ):
            combo = example.combo
            score = 0.0
            if key and key == query_key:
                score += EXACT_PATTERN_WEIGHT
                exacts[combo] += 1

            shared = query_features & features
            text_shared = {f for f in shared if not f.startswith("amt:")}
            if text_shared:
                score += float(len(text_shared))
                matched_words.setdefault(combo, set()).update(
                    f[2:] for f in text_shared if f.startswith("w:")
                )
            if any(f.startswith("amt:") for f in shared):
                score += AMOUNT_FEATURE_WEIGHT

            if score > 0:
                scores[combo] += score
                supports[combo] += 1

        if not scores:
            return SuggestionResult(status="no_matching_history", trained_examples=self.example_count)

        total = sum(scores.values())
        candidates: list[JournalCandidate] = []
        # 同点は科目コードの辞書順で固定する（実行ごとに並びが変わらないこと）。
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        for (debit_codes, credit_codes), score in ranked:
            combo = (debit_codes, credit_codes)
            support = supports[combo]
            if support < self.MIN_SUPPORT and exacts[combo] == 0:
                continue
            confidence = score / total if total > 0 else 0.0
            candidates.append(
                JournalCandidate(
                    debit_codes=debit_codes,
                    credit_codes=credit_codes,
                    confidence=confidence,
                    support=support,
                    exact_matches=exacts[combo],
                    reliable=confidence >= self.RELIABLE_CONFIDENCE and support >= self.MIN_SUPPORT,
                    matched_features=sorted(matched_words.get(combo, set())),
                )
            )
            if len(candidates) >= limit:
                break

        if not candidates:
            return SuggestionResult(status="no_matching_history", trained_examples=self.example_count)
        return SuggestionResult(
            status="ok", trained_examples=self.example_count, candidates=candidates
        )

    # -- 永続化（呼び出し側が保存したい場合の素通し形式） ---------------------

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "examples": [
                {
                    "text": e.text,
                    "amount": str(e.amount),
                    "debit_codes": list(e.debit_codes),
                    "credit_codes": list(e.credit_codes),
                }
                for e in self._examples
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JournalPatternLearner":
        learner = cls()
        for raw in data.get("examples", []):
            learner.add_example(
                JournalExample(
                    text=raw["text"],
                    amount=Decimal(raw["amount"]),
                    debit_codes=tuple(raw["debit_codes"]),
                    credit_codes=tuple(raw["credit_codes"]),
                )
            )
        return learner


# ---------------------------------------------------------------------------
# DB アダプタ: 確定済み仕訳から学習し、科目を解決して候補を返す。
# 学習データは会社ごとに閉じる（他社の仕訳が混ざることは決してない）。
# ---------------------------------------------------------------------------


def _example_from_rows(header: JournalHeader, lines: list[JournalLine], accounts: dict[UUID, Account]) -> JournalExample | None:
    debit_codes = sorted(
        accounts[line.account_id].account_code for line in lines if line.debit_credit == "debit"
    )
    credit_codes = sorted(
        accounts[line.account_id].account_code for line in lines if line.debit_credit == "credit"
    )
    if not debit_codes or not credit_codes:
        return None

    amount = sum(
        (line.amount for line in lines if line.debit_credit == "debit"), Decimal("0")
    )
    text_parts = [header.summary or ""]
    text_parts.extend(line.description or "" for line in lines)
    return JournalExample(
        text=" ".join(part for part in text_parts if part),
        amount=amount,
        debit_codes=tuple(debit_codes),
        credit_codes=tuple(credit_codes),
    )


async def train_from_history(
    db: AsyncSession,
    company_id: UUID,
    *,
    limit: int = 2000,
) -> JournalPatternLearner:
    """その会社の確定済み（posted）仕訳から学習器を構築する。

    下書きや取消済みの仕訳は「正解」ではないため学習に使わない。
    呼び出しのたびに履歴から構築する（学習結果を別テーブルに持たない）ので、
    新しく確定した仕訳は次回の候補提示から自動的に効く。
    """
    headers_result = await db.execute(
        select(JournalHeader)
        .where(
            JournalHeader.company_id == company_id,
            JournalHeader.is_deleted.is_(False),
            JournalHeader.is_voided.is_(False),
            JournalHeader.approval_status == "posted",
        )
        .order_by(JournalHeader.transaction_date.desc())
        .limit(limit)
    )
    headers = list(headers_result.scalars().all())

    learner = JournalPatternLearner()
    if not headers:
        return learner

    header_ids = [h.journal_header_id for h in headers]
    lines_result = await db.execute(
        select(JournalLine, Account)
        .join(Account, JournalLine.account_id == Account.account_id)
        .where(
            JournalLine.journal_header_id.in_(header_ids),
            JournalLine.is_deleted.is_(False),
        )
        .order_by(JournalLine.line_number)
    )
    rows = lines_result.all()

    accounts: dict[UUID, Account] = {}
    lines_by_header: dict[UUID, list[JournalLine]] = {}
    for line, account in rows:
        accounts[account.account_id] = account
        lines_by_header.setdefault(line.journal_header_id, []).append(line)

    for header in headers:
        example = _example_from_rows(header, lines_by_header.get(header.journal_header_id, []), accounts)
        if example is not None:
            learner.add_example(example)

    return learner


async def suggest_from_history(
    db: AsyncSession,
    company_id: UUID,
    *,
    description: str,
    amount: Decimal | None = None,
    partner_name: str | None = None,
    limit: int = 3,
) -> dict:
    """過去仕訳から学習して仕訳候補を返す。候補の科目は ID と名称まで解決する。"""
    learner = await train_from_history(db, company_id)
    text = " ".join(part for part in [description, partner_name or ""] if part)
    result = learner.suggest(text=text, amount=amount, limit=limit)

    response: dict = {
        "status": result.status,
        "trained_examples": result.trained_examples,
        "candidates": [],
    }
    if not result.candidates:
        return response

    wanted_codes = {
        code
        for candidate in result.candidates
        for code in (*candidate.debit_codes, *candidate.credit_codes)
    }
    accounts_result = await db.execute(
        select(Account).where(
            Account.company_id == company_id,
            Account.account_code.in_(wanted_codes),
            Account.is_active.is_(True),
            Account.is_deleted.is_(False),
        )
    )
    accounts_by_code = {a.account_code: a for a in accounts_result.scalars().all()}

    def _resolve(codes: tuple[str, ...]) -> list[dict]:
        resolved = []
        for code in codes:
            account = accounts_by_code.get(code)
            if account is None:
                continue
            resolved.append(
                {
                    "account_id": str(account.account_id),
                    "account_code": account.account_code,
                    "account_name": account.account_name,
                }
            )
        return resolved

    for candidate in result.candidates:
        response["candidates"].append(
            {
                "debit_accounts": _resolve(candidate.debit_codes),
                "credit_accounts": _resolve(candidate.credit_codes),
                "confidence": round(candidate.confidence, 4),
                "support": candidate.support,
                "exact_matches": candidate.exact_matches,
                "reliable": candidate.reliable,
                "matched_features": candidate.matched_features,
            }
        )
    return response
