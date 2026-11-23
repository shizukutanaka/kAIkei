"""仕訳の外部形式への書き出し。

弥生会計の取り込み形式（弥生公式「仕訳データの項目と記述形式」）への変換を、
DB非依存の純粋関数として実装する。形式の要点:

- 1行25項目のカンマ区切り、ヘッダ行なし。
- 借方・貸方が各1行の仕訳は識別フラグ「2000」（伝票以外の仕訳データ）。
- 複数行の仕訳は伝票形式: 1行目「2110」・中間の行「2100」・最終行「2101」。
  片側しかない行は、空いた側の税区分に「対象外」、金額に「0」を入れる（必須項目）。
- 税区分は必須項目。仕訳明細に税ルールが付いていればその名称を使い、
  無ければ「対象外」とする。
- 金額・消費税金額は整数（円）。四捨五入で円未満を丸める。
- 摘要は64文字で切り捨てられる仕様のため、こちらで先に64文字へ丸める。
- タイプは「0」（仕訳データ）、調整は「no」。
- 伝票Noは弥生側の付番に任せるため空欄にする（自社の仕訳番号は JRN- 形式で
  弥生の伝票No（数字6桁以内）には入らない）。
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core.csv_export import csv_line

YAYOI_COLUMN_COUNT = 25
DEFAULT_TAX_CATEGORY = "対象外"


@dataclass(frozen=True)
class ExportLine:
    debit_credit: str  # "debit" | "credit"
    account_name: str
    sub_account_name: str = ""
    amount: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    tax_category: str = DEFAULT_TAX_CATEGORY
    description: str = ""


@dataclass(frozen=True)
class ExportJournal:
    transaction_date: date
    summary: str = ""
    lines: list[ExportLine] = field(default_factory=list)


def _yen(amount: Decimal) -> str:
    """金額を円単位の整数文字列にする（弥生形式は整数必須）。"""
    return str(Decimal(amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _date_text(value) -> str:
    return value.strftime("%Y/%m/%d")


def _row(
    *,
    flag: str,
    journal: ExportJournal,
    debit: ExportLine | None,
    credit: ExportLine | None,
    summary: str,
) -> list[str]:
    row = [""] * YAYOI_COLUMN_COUNT
    row[0] = flag
    # row[1] 伝票No: 弥生側の付番に任せるため空欄
    # row[2] 決算: 通常の仕訳なので空欄
    row[3] = _date_text(journal.transaction_date)
    if debit is not None:
        row[4] = debit.account_name
        row[5] = debit.sub_account_name
        row[7] = debit.tax_category or DEFAULT_TAX_CATEGORY
        row[8] = _yen(debit.amount)
        row[9] = _yen(debit.tax_amount)
    else:
        row[7] = DEFAULT_TAX_CATEGORY
        row[8] = "0"
        row[9] = "0"
    if credit is not None:
        row[10] = credit.account_name
        row[11] = credit.sub_account_name
        row[13] = credit.tax_category or DEFAULT_TAX_CATEGORY
        row[14] = _yen(credit.amount)
        row[15] = _yen(credit.tax_amount)
    else:
        row[13] = DEFAULT_TAX_CATEGORY
        row[14] = "0"
        row[15] = "0"
    row[16] = (summary or "")[:64]
    row[19] = "0"  # タイプ: 仕訳データ
    row[24] = "no"  # 調整: チェックを付けない
    return row


def build_yayoi_rows(journals: list[ExportJournal]) -> list[list[str]]:
    """仕訳の列を弥生形式の25項目の行へ変換する。"""
    rows: list[list[str]] = []
    for journal in journals:
        debits = [line for line in journal.lines if line.debit_credit == "debit"]
        credits = [line for line in journal.lines if line.debit_credit == "credit"]
        if len(debits) == 1 and len(credits) == 1:
            rows.append(
                _row(flag="2000", journal=journal, debit=debits[0], credit=credits[0], summary=journal.summary)
            )
            continue
        # 複合仕訳は伝票形式（2110/2100/2101）で1行に片側ずつ出す。
        ordered = [*debits, *credits]
        for index, line in enumerate(ordered):
            flag = "2110" if index == 0 else "2101" if index == len(ordered) - 1 else "2100"
            rows.append(
                _row(
                    flag=flag,
                    journal=journal,
                    debit=line if line.debit_credit == "debit" else None,
                    credit=line if line.debit_credit == "credit" else None,
                    summary=line.description or journal.summary,
                )
            )
    return rows


def build_yayoi_csv(journals: list[ExportJournal]) -> str:
    """弥生形式のCSV文字列を作る（文字コード変換は呼び出し側で行う）。"""
    return "\r\n".join(csv_line(row) for row in build_yayoi_rows(journals))
