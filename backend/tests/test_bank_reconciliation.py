from datetime import date
from decimal import Decimal

import pytest

from app.services.bank_reconciliation import (
    ReconciliationCandidate,
    find_best_match,
    match_score,
    name_similarity,
    normalize_name,
    parse_bank_csv,
)


class TestNormalizeName:
    def test_strips_corporate_tokens_and_spaces(self):
        assert normalize_name("株式会社 カイケイ商事") == normalize_name("カイケイ商事")

    def test_uppercases(self):
        assert normalize_name("abc corp") == normalize_name("ABC CORP")

    def test_none_and_empty(self):
        assert normalize_name(None) == ""
        assert normalize_name("") == ""

    def test_strips_furikomi_marker(self):
        assert normalize_name("カ)カイケイ") == normalize_name("カイケイ")


class TestNameSimilarity:
    def test_identical_after_normalization(self):
        assert name_similarity("株式会社カイケイ", "カイケイ") == 1.0

    def test_empty_is_zero(self):
        assert name_similarity("", "カイケイ") == 0.0
        assert name_similarity(None, None) == 0.0

    def test_similar_scores_higher_than_different(self):
        sim_close = name_similarity("カイケイショウジ", "カイケイショウカイ")
        sim_far = name_similarity("カイケイ", "ゼンゼンチガウ")
        assert sim_close > sim_far


class TestMatchScore:
    def _cand(self, amount, d, name=""):
        return ReconciliationCandidate(ref_id="c1", amount=Decimal(amount), date=d, counterparty_name=name)

    def test_amount_mismatch_returns_none(self):
        cand = self._cand("10000", date(2026, 4, 15))
        assert match_score(Decimal("9999"), date(2026, 4, 15), "", cand) is None

    def test_date_beyond_tolerance_returns_none(self):
        cand = self._cand("10000", date(2026, 4, 1))
        assert match_score(Decimal("10000"), date(2026, 4, 15), "", cand, date_tolerance_days=3) is None

    def test_same_day_same_name_scores_high(self):
        cand = self._cand("10000", date(2026, 4, 15), "カイケイ商事")
        score = match_score(Decimal("10000"), date(2026, 4, 15), "株式会社カイケイ商事", cand)
        assert score == pytest.approx(1.0)

    def test_date_proximity_reduces_score(self):
        cand = self._cand("10000", date(2026, 4, 13), "カイケイ")
        near = match_score(Decimal("10000"), date(2026, 4, 15), "カイケイ", self._cand("10000", date(2026, 4, 15), "カイケイ"))
        far = match_score(Decimal("10000"), date(2026, 4, 15), "カイケイ", cand)
        assert near > far

    def test_zero_tolerance_requires_exact_date(self):
        cand = self._cand("10000", date(2026, 4, 14), "カイケイ")
        # 1日差は許容0では不一致
        assert match_score(Decimal("10000"), date(2026, 4, 15), "カイケイ", cand, date_tolerance_days=0) is None
        # 同日は一致
        same = self._cand("10000", date(2026, 4, 15), "カイケイ")
        assert match_score(Decimal("10000"), date(2026, 4, 15), "カイケイ", same, date_tolerance_days=0) is not None


class TestFindBestMatch:
    def test_picks_highest_score(self):
        cands = [
            ReconciliationCandidate("a", Decimal("10000"), date(2026, 4, 15), "チガウナマエ"),
            ReconciliationCandidate("b", Decimal("10000"), date(2026, 4, 15), "カイケイ商事"),
        ]
        best = find_best_match(Decimal("10000"), date(2026, 4, 15), "カイケイ商事", cands)
        assert best is not None
        assert best[0].ref_id == "b"

    def test_returns_none_when_all_below_min_score(self):
        cands = [ReconciliationCandidate("a", Decimal("10000"), date(2026, 4, 15), "X")]
        best = find_best_match(
            Decimal("10000"), date(2026, 4, 15), "Y", cands, min_score=0.99, name_weight=1.0
        )
        assert best is None

    def test_returns_none_when_no_amount_match(self):
        cands = [ReconciliationCandidate("a", Decimal("500"), date(2026, 4, 15), "カイケイ")]
        assert find_best_match(Decimal("10000"), date(2026, 4, 15), "カイケイ", cands) is None

    def test_tie_break_prefers_closer_date(self):
        # 同名・同スコアなら日付が近い方を選ぶ
        cands = [
            ReconciliationCandidate("far", Decimal("10000"), date(2026, 4, 12), "カイケイ"),
            ReconciliationCandidate("near", Decimal("10000"), date(2026, 4, 15), "カイケイ"),
        ]
        best = find_best_match(Decimal("10000"), date(2026, 4, 15), "カイケイ", cands)
        assert best[0].ref_id == "near"


class TestParseBankCsv:
    def test_parses_deposit_and_withdrawal(self):
        csv_text = (
            "取引日,入金額,出金額,残高,摘要,振込人名カナ\n"
            "2026/04/15,\"10,000\",,\"110,000\",振込入金,カ)カイケイ\n"
            "2026/04/16,,\"3,000\",\"107,000\",引落,デンキダイ\n"
        )
        rows = parse_bank_csv(csv_text)
        assert len(rows) == 2
        assert rows[0].direction == "deposit"
        assert rows[0].amount == Decimal("10000")
        assert rows[0].counterparty_name == "カ)カイケイ"
        assert rows[1].direction == "withdrawal"
        assert rows[1].amount == Decimal("3000")

    def test_skips_bad_date(self):
        csv_text = "取引日,入金額,出金額,残高,摘要,振込人名カナ\nNOTADATE,1000,,,x,y\n"
        assert parse_bank_csv(csv_text) == []

    def test_skips_row_with_no_amount(self):
        csv_text = "取引日,入金額,出金額,残高,摘要,振込人名カナ\n2026/04/15,,,100,x,y\n"
        assert parse_bank_csv(csv_text) == []

class TestFeeTolerance:
    def _cand(self, amount, d=None, name="カイケイ"):
        from datetime import date as _date
        return ReconciliationCandidate(ref_id="c1", amount=Decimal(amount), date=d or _date(2026, 4, 15), counterparty_name=name)

    def test_no_tolerance_rejects_fee_difference(self):
        from datetime import date as _date
        cand = self._cand("10000")
        # 手数料880円引かれた入金は、許容0では不一致
        assert match_score(Decimal("9120"), _date(2026, 4, 15), "カイケイ", cand) is None

    def test_tolerance_allows_fee_difference(self):
        from datetime import date as _date
        cand = self._cand("10000")
        score = match_score(Decimal("9120"), _date(2026, 4, 15), "カイケイ", cand, amount_tolerance=Decimal("880"))
        assert score is not None

    def test_tolerance_still_rejects_beyond_fee(self):
        from datetime import date as _date
        cand = self._cand("10000")
        assert match_score(Decimal("9000"), _date(2026, 4, 15), "カイケイ", cand, amount_tolerance=Decimal("880")) is None

    def test_exact_match_preferred_over_fee_match(self):
        from datetime import date as _date
        exact = ReconciliationCandidate(ref_id="exact", amount=Decimal("9120"), date=_date(2026, 4, 15), counterparty_name="カイケイ")
        feeish = ReconciliationCandidate(ref_id="fee", amount=Decimal("10000"), date=_date(2026, 4, 15), counterparty_name="カイケイ")
        best = find_best_match(Decimal("9120"), _date(2026, 4, 15), "カイケイ", [feeish, exact], amount_tolerance=Decimal("880"))
        assert best is not None and best[0].ref_id == "exact"


class TestZenginNameNormalization:
    """全銀協フォーマット由来の半角カナ振込人名を突合できること。

    銀行連携の振込依頼人名は半角カタカナ、取引先マスタは全角カナ/漢字で登録される。
    NFKC正規化前は両者の類似度が0となり、名称による自動消込が一切成立しなかった。
    """

    def test_halfwidth_kana_matches_fullwidth(self):
        assert name_similarity("ﾀﾅｶｼｮｳｼﾞ", "タナカショウジ") == 1.0

    def test_voiced_marks_are_composed(self):
        # 半角の濁点は結合文字（"ｶ"+"ﾞ"）。NFKCで"ガ"に合成される。
        assert normalize_name("ｶﾞｲｼﾔ") == "ガイシヤ"
        assert name_similarity("ｽｽﾞｷ", "スズキ") == 1.0

    def test_halfwidth_legal_abbreviation_prefix(self):
        # 前株: "ｶ)ﾀﾅｶ"
        assert name_similarity("ｶ)ﾀﾅｶ", "タナカ") == 1.0

    def test_halfwidth_legal_abbreviation_suffix(self):
        # 後株: "ﾀﾅｶ(ｶ"
        assert name_similarity("ﾀﾅｶ(ｶ", "タナカ") == 1.0

    def test_other_legal_abbreviations(self):
        assert name_similarity("ﾕ)ﾀﾅｶ", "有限会社タナカ") == 1.0     # 有限会社
        assert name_similarity("ﾄﾞ)ﾀﾅｶ", "合同会社タナカ") == 1.0    # 合同会社
        assert name_similarity("ｲ)ｻｸﾗ", "医療法人サクラ") == 1.0     # 医療法人

    def test_fullwidth_alphanumeric_normalized(self):
        assert name_similarity("ＡＢＣ商事", "ABC商事") == 1.0

    def test_distinct_names_still_do_not_match(self):
        # 正規化を強めても別会社が同一視されないこと（誤消込の防止）。
        # 判定境界は消込側の名称閾値(DEFAULT_NAME_THRESHOLD=0.6)。共通語尾"ショウ"により
        # 0ではないが、閾値未満に留まり同一取引先とは扱われない。
        assert name_similarity("ｽｽﾞｷｼｮｳﾃﾝ", "タナカショウジ") < 0.6

    def test_bare_abbreviation_kana_is_preserved(self):
        # 括弧なしの"カ"は社名の一部。除去してはいけない。
        assert "カ" in normalize_name("ｶﾜｸﾞﾁ")
        assert normalize_name("ｶﾜｸﾞﾁ") == "カワグチ"
