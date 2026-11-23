"""銀行明細CSVの汎用取り込み（文字コード・日付・列対応・読み飛ばし報告）のテスト。

金銭データの取り込みで最も悪いのは「黙って行が消える」こと。読めなかった行は
必ず理由つきで返ること、銀行ごとに違うファイル形式（Shift_JIS、日付表記、
列名、金額1列形式）を吸収できることを固定する。
"""
from datetime import date
from decimal import Decimal

from app.services.bank_reconciliation import (
    decode_statement_bytes,
    parse_bank_csv,
    parse_bank_csv_detailed,
)

HEADER = "取引日,入金額,出金額,残高,摘要,振込人名カナ\n"


class TestDecodeStatementBytes:
    def test_utf8_with_bom(self):
        text = "取引日,入金額\n2026/04/15,1000\n"
        assert decode_statement_bytes(text.encode("utf-8-sig")) == text

    def test_shift_jis(self):
        text = "取引日,入金額\n2026/04/15,1000\n"
        assert decode_statement_bytes(text.encode("cp932")) == text

    def test_undecodable_raises_with_reason(self):
        import pytest

        with pytest.raises(ValueError, match="文字コード"):
            decode_statement_bytes(b"\xff\xfe\x00\x01\x82\x83\x84")


class TestDateFormats:
    def _parse_one(self, date_text: str):
        result = parse_bank_csv_detailed(HEADER + f"{date_text},1000,,5000,入金,テスト\n")
        assert result.skipped == []
        return result.rows[0].transaction_date

    def test_slash(self):
        assert self._parse_one("2026/04/15") == date(2026, 4, 15)

    def test_slash_single_digits(self):
        assert self._parse_one("2026/4/5") == date(2026, 4, 5)

    def test_dash(self):
        assert self._parse_one("2026-04-15") == date(2026, 4, 15)

    def test_compact(self):
        assert self._parse_one("20260415") == date(2026, 4, 15)

    def test_japanese_separated(self):
        assert self._parse_one("2026年4月15日") == date(2026, 4, 15)

    def test_era_reiwa(self):
        assert self._parse_one("R08/04/15") == date(2026, 4, 15)
        assert self._parse_one("令和8年4月15日") == date(2026, 4, 15)

    def test_era_heisei(self):
        assert self._parse_one("H31/04/30") == date(2019, 4, 30)

    def test_fullwidth_digits(self):
        assert self._parse_one("２０２６/０４/１５") == date(2026, 4, 15)

    def test_bad_date_is_reported_not_dropped(self):
        result = parse_bank_csv_detailed(HEADER + "15/04/2026,1000,,5000,入金,テスト\n")
        assert result.rows == []
        assert len(result.skipped) == 1
        assert result.skipped[0].row_number == 2
        assert "日付" in result.skipped[0].reason


class TestColumnVariations:
    def test_bank_specific_headers(self):
        # お預り金額/お支払金額 型の列名（大手銀行のCSVで使われる表記）
        csv_text = (
            "日付,お支払金額,お預り金額,お取引後残高,お取引内容\n"
            "2026/04/15,,10000,110000,振込 テスト\n"
            "2026/04/16,3000,,107000,引落 デンキ\n"
        )
        result = parse_bank_csv_detailed(csv_text)
        assert result.skipped == []
        assert [r.direction for r in result.rows] == ["deposit", "withdrawal"]
        assert result.rows[0].amount == Decimal("10000")

    def test_column_map_override(self):
        csv_text = "年月日,入,出,コメント\n2026/04/15,1000,,テスト\n"
        result = parse_bank_csv_detailed(
            csv_text,
            column_map={"date": "年月日", "deposit": "入", "withdrawal": "出", "description": "コメント"},
        )
        assert result.skipped == []
        assert result.rows[0].amount == Decimal("1000")
        assert result.rows[0].description == "テスト"

    def test_single_amount_with_direction_column(self):
        csv_text = (
            "日付,入出金区分,金額,摘要\n"
            "2026/04/15,入金,10000,振込\n"
            "2026/04/16,出金,3000,引落\n"
        )
        result = parse_bank_csv_detailed(csv_text)
        assert result.skipped == []
        assert [(r.direction, r.amount) for r in result.rows] == [
            ("deposit", Decimal("10000")),
            ("withdrawal", Decimal("3000")),
        ]

    def test_single_amount_negative_is_withdrawal(self):
        csv_text = "日付,金額,摘要\n2026/04/15,-3000,カード利用\n"
        result = parse_bank_csv_detailed(csv_text)
        assert result.skipped == []
        assert result.rows[0].direction == "withdrawal"
        assert result.rows[0].amount == Decimal("3000")

    def test_single_amount_positive_without_direction_is_reported(self):
        # 方向が決められない行を、勝手に入金として取り込むことはしない。
        csv_text = "日付,金額,摘要\n2026/04/15,3000,不明\n"
        result = parse_bank_csv_detailed(csv_text)
        assert result.rows == []
        assert len(result.skipped) == 1
        assert "方向" in result.skipped[0].reason

    def test_both_amounts_is_reported(self):
        result = parse_bank_csv_detailed(HEADER + "2026/04/15,1000,500,5000,混在,テスト\n")
        assert result.rows == []
        assert len(result.skipped) == 1
        assert "両方" in result.skipped[0].reason

    def test_no_amount_is_reported(self):
        result = parse_bank_csv_detailed(HEADER + "2026/04/15,,,5000,空,テスト\n")
        assert result.rows == []
        assert len(result.skipped) == 1

    def test_trailing_blank_lines_are_ignored(self):
        result = parse_bank_csv_detailed(HEADER + "2026/04/15,1000,,5000,入金,テスト\n\n\n")
        assert len(result.rows) == 1
        assert result.skipped == []

    def test_parse_bank_csv_compat_returns_only_rows(self):
        rows = parse_bank_csv(HEADER + "2026/04/15,1000,,5000,入金,テスト\nBAD,1,,2,x,y\n")
        assert len(rows) == 1
