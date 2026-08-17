"""CSV出力ユーティリティの回帰テスト。

f文字列連結によるCSV生成で起きていた「列ずれ」「行注入」「数式インジェクション」を
再発させないことを固定する。
"""

import csv
import io

from app.core.csv_export import csv_document, csv_line, escape_formula

HEADER = ["取引No", "取引日", "借方勘目", "摘要", "金額", "税区分"]


def _parse(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


class TestColumnIntegrity:
    """列ずれ（データ破損）を起こさないこと。"""

    def test_comma_in_summary_does_not_shift_columns(self):
        # 「売上計上, 東京支店分」は日本語の実務で普通に現れる表記。
        row = ["J001", "2026-06-30", "現金", "売上計上, 東京支店分", "10000", "対象外"]
        parsed = _parse(csv_document(HEADER, [row]))
        assert len(parsed[1]) == len(HEADER)
        assert parsed[1][3] == "売上計上, 東京支店分"
        assert parsed[1][4] == "10000"  # 金額が正しい列に残る

    def test_newline_in_field_does_not_inject_rows(self):
        malicious = "売上計上\nJ999,2026-01-01,現金,不正行,999999,対象外"
        parsed = _parse(csv_document(HEADER, [["J001", "2026-06-30", "現金", malicious, "10000", "対象外"]]))
        # ヘッダ + 明細1行のみ（改行はフィールド内に閉じ込められる）
        assert len(parsed) == 2
        assert parsed[1][3] == malicious
        assert parsed[1][4] == "10000"

    def test_quotes_are_escaped(self):
        parsed = _parse(csv_document(HEADER, [["J001", "2026-06-30", "現金", '摘要"引用"付き', "10000", "対象外"]]))
        assert parsed[1][3] == '摘要"引用"付き'
        assert len(parsed[1]) == len(HEADER)


class TestFormulaInjection:
    """Excel/LibreOffice で数式として解釈されないこと（OWASP CSV Injection）。"""

    def test_dangerous_prefixes_are_neutralised(self):
        for payload in ('=cmd|\'/c calc\'!A1', "=1+1", "@SUM(A1)", "\tfoo", "\rbar"):
            assert escape_formula(payload).startswith("'"), payload

    def test_plain_text_is_untouched(self):
        assert escape_formula("売上計上") == "売上計上"
        assert escape_formula("") == ""
        assert escape_formula(None) == ""

    def test_formula_is_neutralised_in_document(self):
        parsed = _parse(csv_document(HEADER, [["J001", "2026-06-30", "現金", "=cmd|'/c calc'!A1", "10000", "対象外"]]))
        assert parsed[1][3].startswith("'=")


class TestNumericValuesPreserved:
    """会計データの数値、特に負数を壊さないこと。"""

    def test_negative_amounts_are_not_quoted(self):
        # 先頭が "-" だが数値。'-1000 になると集計できなくなる。
        for amount in ("-1000", "-1000.50", "-0.01"):
            assert escape_formula(amount) == amount

    def test_positive_and_decimal_numbers_untouched(self):
        for amount in ("1000", "0", "1234.56", "+500"):
            assert escape_formula(amount) == amount

    def test_negative_amount_survives_roundtrip(self):
        parsed = _parse(csv_document(HEADER, [["J001", "2026-06-30", "現金", "返品", "-10000", "対象外"]]))
        assert parsed[1][4] == "-10000"

    def test_non_numeric_leading_minus_is_neutralised(self):
        # 数値でない "-" 始まりは数式になりうるので無害化する。
        assert escape_formula("-cmd|'/c calc'!A1").startswith("'")


class TestCsvLine:
    def test_single_line_has_no_trailing_newline(self):
        assert "\n" not in csv_line(["a", "b", "c"])
        assert csv_line(["a", "b", "c"]) == "a,b,c"

    def test_empty_and_none_fields(self):
        assert csv_line(["a", "", None, "d"]) == "a,,,d"
