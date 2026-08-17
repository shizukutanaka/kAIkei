"""CSV出力の共通ユーティリティ。

CSVをf文字列の連結で組み立てると、次の3つの問題が同時に起きる。

1. **列ずれ（データ破損）**: 摘要や取引先名にカンマが含まれると列が増え、以降の値が
   ひとつずつ隣の列へずれる。「売上計上, 東京支店分」のような表記は日本語の実務では
   普通に現れるため、金額が税区分の列に入るなどして**誤った内容が会計ソフトへ取り込まれる**。
2. **行注入**: 改行を含む値があると1行が複数行に分割され、任意の行を差し込める。
3. **数式インジェクション（CSV Injection）**: `=`,`+`,`-`,`@`,タブ,復帰 で始まる値は
   Excel/LibreOffice が数式として解釈する。DDEを悪用すると閲覧者の端末で外部プログラムが
   起動しうる（OWASP "CSV Injection"）。会計データは監査法人や税理士がExcelで開くため
   実害に直結する。

1・2 はRFC 4180準拠のクォート（`csv`モジュール）で、3 は先頭への `'` 付与で防ぐ。

**数値の扱い**: 会計データには負数（例: `-1000`）が普通に現れる。先頭が `-` だからと
一律にクォートすると金額が文字列 `'-1000` になり集計できなくなるため、
数値として解釈できる値は数式扱いしない。
"""

import csv
import io
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

# Excel/LibreOffice が数式・コマンドとして解釈しうる先頭文字。
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _is_numeric(text: str) -> bool:
    """会計上の数値（負数・小数を含む）として解釈できるか。"""
    try:
        Decimal(text)
    except (InvalidOperation, ValueError, ArithmeticError):
        return False
    return True


def escape_formula(value: object) -> str:
    """数式として解釈されうる値の先頭に `'` を付けて無害化する。

    数値（負数を含む）はそのまま返す。会計データの金額を壊さないため。
    """
    text = "" if value is None else str(value)
    if not text:
        return text
    if text[0] in _FORMULA_PREFIXES and not _is_numeric(text):
        return "'" + text
    return text


def csv_line(fields: Iterable[object]) -> str:
    """1行分のCSVを組み立てる（RFC 4180のクォート＋数式無害化）。"""
    buffer = io.StringIO()
    # lineterminator を空にして、行の連結は呼び出し側に委ねる。
    writer = csv.writer(buffer, lineterminator="")
    writer.writerow([escape_formula(field) for field in fields])
    return buffer.getvalue()


def csv_document(header: Iterable[object], rows: Iterable[Iterable[object]]) -> str:
    """ヘッダ行と明細行からCSV全体を組み立てる。"""
    lines = [csv_line(header)]
    lines.extend(csv_line(row) for row in rows)
    return "\n".join(lines)
