"""弥生会計取り込み形式への書き出しテスト。

形式は弥生公式「仕訳データの項目と記述形式」に基づく（25項目・識別フラグ・
税区分必須・金額は整数）。金額や列数が崩れると会計ソフト側で誤って取り込まれる
ため、構造をここで固定する。
"""
import csv
import io
from datetime import date
from decimal import Decimal

from app.services.journal_export import ExportJournal, ExportLine, build_yayoi_csv, build_yayoi_rows


def _parse(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def _simple_journal() -> ExportJournal:
    return ExportJournal(
        transaction_date=date(2026, 4, 15),
        summary="家賃の支払い",
        lines=[
            ExportLine(debit_credit="debit", account_name="地代家賃", amount=Decimal("110000")),
            ExportLine(debit_credit="credit", account_name="普通預金", amount=Decimal("110000")),
        ],
    )


class TestSimpleJournal:
    def test_single_row_25_columns_flag_2000(self):
        rows = _parse(build_yayoi_csv([_simple_journal()]))
        assert len(rows) == 1
        row = rows[0]
        assert len(row) == 25
        assert row[0] == "2000"
        assert row[3] == "2026/04/15"
        assert row[4] == "地代家賃"
        assert row[7] == "対象外"  # 税区分は必須項目。ルールが無ければ対象外
        assert row[8] == "110000"
        assert row[10] == "普通預金"
        assert row[13] == "対象外"
        assert row[14] == "110000"
        assert row[16] == "家賃の支払い"
        assert row[19] == "0"  # タイプ: 仕訳データ
        assert row[24] == "no"  # 調整

    def test_tax_rule_name_is_used_when_present(self):
        journal = ExportJournal(
            transaction_date=date(2026, 4, 15),
            summary="売上",
            lines=[
                ExportLine(debit_credit="debit", account_name="売掛金", amount=Decimal("11000")),
                ExportLine(
                    debit_credit="credit", account_name="売上高", amount=Decimal("11000"),
                    tax_category="課税売上 10%", tax_amount=Decimal("1000"),
                ),
            ],
        )
        row = _parse(build_yayoi_csv([journal]))[0]
        assert row[13] == "課税売上 10%"
        assert row[15] == "1000"

    def test_amount_is_rounded_to_integer_yen(self):
        journal = ExportJournal(
            transaction_date=date(2026, 4, 15),
            lines=[
                ExportLine(debit_credit="debit", account_name="消耗品費", amount=Decimal("1000.5")),
                ExportLine(debit_credit="credit", account_name="現金", amount=Decimal("1000.5")),
            ],
        )
        row = _parse(build_yayoi_csv([journal]))[0]
        assert row[8] == "1001"
        assert row[14] == "1001"

    def test_summary_truncated_to_64_chars(self):
        journal = _simple_journal()
        journal = ExportJournal(
            transaction_date=journal.transaction_date,
            summary="あ" * 100,
            lines=journal.lines,
        )
        row = _parse(build_yayoi_csv([journal]))[0]
        assert len(row[16]) == 64

    def test_formula_like_summary_is_escaped(self):
        journal = ExportJournal(
            transaction_date=date(2026, 4, 15),
            summary="=SUM(A1:A2)",
            lines=_simple_journal().lines,
        )
        row = _parse(build_yayoi_csv([journal]))[0]
        assert row[16] == "'=SUM(A1:A2)"


class TestCompoundJournal:
    def test_multi_line_uses_slip_flags(self):
        journal = ExportJournal(
            transaction_date=date(2026, 4, 15),
            summary="給与支払",
            lines=[
                ExportLine(debit_credit="debit", account_name="給料手当", amount=Decimal("300000"), description="給与"),
                ExportLine(debit_credit="debit", account_name="法定福利費", amount=Decimal("40000"), description="社保"),
                ExportLine(debit_credit="credit", account_name="普通預金", amount=Decimal("340000"), description="振込"),
            ],
        )
        rows = build_yayoi_rows([journal])
        assert [r[0] for r in rows] == ["2110", "2100", "2101"]
        assert all(len(r) == 25 for r in rows)
        # 片側だけの行は、空いた側の税区分=対象外・金額=0 が必須
        assert rows[0][10] == "" and rows[0][13] == "対象外" and rows[0][14] == "0"
        assert rows[2][4] == "" and rows[2][7] == "対象外" and rows[2][8] == "0"
        assert rows[2][10] == "普通預金" and rows[2][14] == "340000"

    def test_empty_input(self):
        assert build_yayoi_csv([]) == ""
