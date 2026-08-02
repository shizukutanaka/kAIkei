"""全銀協 総合振込フォーマット(固定長120バイト)の振込データ生成。

支払・納付タスクが確定しても、担当者がネットバンキングに1件ずつ手入力する工程が残る。
総合振込データを作れば一括アップロードで済むが、銀行に受理されるには次の制約を満たす必要があり、
ここが手作業・自作CSVで最も落ちる。

    1. 使える文字が JIS X 0201(半角カナ・英大文字・数字・限られた記号)に限定される
       「株式会社ｶｲｹｲ商事」のような全角/漢字混在の口座名義はそのままでは送れない
    2. 1レコード120バイト固定・区切り文字なし。金額は右詰ゼロ埋め、名称は左詰スペース埋め
    3. ヘッダ(1)・データ(2)・トレーラ(8)・エンド(9)の4区分で、トレーラの件数/金額が明細と一致していること

本サービスは全角カナ・ひらがな・全角英数を半角へ機械変換し、変換しても表現できない文字(漢字等)は
握りつぶさず `ValueError` にする。銀行側でエラーになると振込日に間に合わないため、マスタ修正を
データ作成時点で促すのが正しい。振込手数料の先方負担も金額計算に織り込む(先方負担=振込金額から控除)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

RECORD_LENGTH = 120
ENCODING = "cp932"

RECORD_TYPE_HEADER = "1"
RECORD_TYPE_DATA = "2"
RECORD_TYPE_TRAILER = "8"
RECORD_TYPE_END = "9"

# 種別コード 21 = 総合振込
CATEGORY_CODE_TRANSFER = "21"
# コード区分 0 = JIS
CHAR_CODE_JIS = "0"
# 振込指定区分 7 = テレ振込
TRANSFER_METHOD_TELEGRAPHIC = "7"
# 新規コード 0 = その他(新規・変更以外)
NEW_CODE_OTHER = "0"

ACCOUNT_TYPE_ORDINARY = "1"
ACCOUNT_TYPE_CHECKING = "2"
ACCOUNT_TYPE_SAVINGS = "4"
_ACCOUNT_TYPES = frozenset({ACCOUNT_TYPE_ORDINARY, ACCOUNT_TYPE_CHECKING, ACCOUNT_TYPE_SAVINGS})

_ZERO = Decimal("0")

# 全銀で使用できる記号(JIS X 0201 の部分集合)。
_ALLOWED_SYMBOLS = frozenset(" .()-/¥,\"")

_KANA_HALF: dict[str, str] = {
    "ア": "ｱ", "イ": "ｲ", "ウ": "ｳ", "エ": "ｴ", "オ": "ｵ",
    "カ": "ｶ", "キ": "ｷ", "ク": "ｸ", "ケ": "ｹ", "コ": "ｺ",
    "サ": "ｻ", "シ": "ｼ", "ス": "ｽ", "セ": "ｾ", "ソ": "ｿ",
    "タ": "ﾀ", "チ": "ﾁ", "ツ": "ﾂ", "テ": "ﾃ", "ト": "ﾄ",
    "ナ": "ﾅ", "ニ": "ﾆ", "ヌ": "ﾇ", "ネ": "ﾈ", "ノ": "ﾉ",
    "ハ": "ﾊ", "ヒ": "ﾋ", "フ": "ﾌ", "ヘ": "ﾍ", "ホ": "ﾎ",
    "マ": "ﾏ", "ミ": "ﾐ", "ム": "ﾑ", "メ": "ﾒ", "モ": "ﾓ",
    "ヤ": "ﾔ", "ユ": "ﾕ", "ヨ": "ﾖ",
    "ラ": "ﾗ", "リ": "ﾘ", "ル": "ﾙ", "レ": "ﾚ", "ロ": "ﾛ",
    "ワ": "ﾜ", "ヲ": "ｦ", "ン": "ﾝ",
    "ガ": "ｶﾞ", "ギ": "ｷﾞ", "グ": "ｸﾞ", "ゲ": "ｹﾞ", "ゴ": "ｺﾞ",
    "ザ": "ｻﾞ", "ジ": "ｼﾞ", "ズ": "ｽﾞ", "ゼ": "ｾﾞ", "ゾ": "ｿﾞ",
    "ダ": "ﾀﾞ", "ヂ": "ﾁﾞ", "ヅ": "ﾂﾞ", "デ": "ﾃﾞ", "ド": "ﾄﾞ",
    "バ": "ﾊﾞ", "ビ": "ﾋﾞ", "ブ": "ﾌﾞ", "ベ": "ﾍﾞ", "ボ": "ﾎﾞ",
    "パ": "ﾊﾟ", "ピ": "ﾋﾟ", "プ": "ﾌﾟ", "ペ": "ﾍﾟ", "ポ": "ﾎﾟ",
    "ヴ": "ｳﾞ",
    # 小書き文字は全銀では大文字扱い。
    "ァ": "ｱ", "ィ": "ｲ", "ゥ": "ｳ", "ェ": "ｴ", "ォ": "ｵ",
    "ッ": "ﾂ", "ャ": "ﾔ", "ュ": "ﾕ", "ョ": "ﾖ", "ヮ": "ﾜ",
    "ー": "-", "・": ".", "、": ",", "。": ".",
    "゛": "ﾞ", "゜": "ﾟ",
    "　": " ",
}

_SYMBOL_HALF: dict[str, str] = {
    "（": "(", "）": ")", "－": "-", "ー": "-", "／": "/", "￥": "¥",
    "．": ".", "，": ",", "”": '"', "＼": "¥",
}


@dataclass(frozen=True)
class TransferLine:
    bank_code: str
    bank_name: str
    branch_code: str
    branch_name: str
    account_type: str
    account_number: str
    recipient_name: str
    amount: Decimal
    customer_code: str = ""
    fee_borne_by_recipient: bool = False
    transfer_fee: Decimal = _ZERO


@dataclass(frozen=True)
class TransferRequest:
    consignor_code: str
    consignor_name: str
    transfer_date: date
    bank_code: str
    bank_name: str
    branch_code: str
    branch_name: str
    account_type: str
    account_number: str
    lines: list[TransferLine] = field(default_factory=list)


@dataclass(frozen=True)
class TransferLineResult:
    recipient_name: str
    payable_amount: Decimal
    transfer_fee: Decimal
    transfer_amount: Decimal
    fee_borne_by_recipient: bool


@dataclass(frozen=True)
class ZenginTransferResult:
    records: list[str]
    detail_count: int
    total_amount: Decimal
    total_fee_deducted: Decimal
    lines: list[TransferLineResult]
    encoding: str
    record_length: int


class ZenginTransferService:
    """総合振込データを生成する純粋サービス。"""

    @staticmethod
    def to_zengin_charset(value: str) -> str:
        """全角カナ・ひらがな・全角英数を半角へ変換し、使用不可文字を検出する。"""
        converted: list[str] = []
        for char in value:
            if char in _KANA_HALF:
                converted.append(_KANA_HALF[char])
                continue
            if char in _SYMBOL_HALF:
                converted.append(_SYMBOL_HALF[char])
                continue
            if "ぁ" <= char <= "ゖ":
                katakana = chr(ord(char) + 0x60)
                if katakana in _KANA_HALF:
                    converted.append(_KANA_HALF[katakana])
                    continue
            if "０" <= char <= "９" or "Ａ" <= char <= "Ｚ" or "ａ" <= char <= "ｚ":
                converted.append(chr(ord(char) - 0xFEE0).upper())
                continue
            converted.append(char.upper())

        result = "".join(converted)
        invalid = sorted(
            {
                char
                for char in result
                if not (
                    char.isascii() and (char.isalnum() or char in _ALLOWED_SYMBOLS)
                )
                and not ("｡" <= char <= "ﾟ")
            }
        )
        if invalid:
            raise ValueError(
                "zengin charset does not allow: " + "".join(invalid) + f" (in '{value}')"
            )
        return result

    @classmethod
    def _text(cls, value: str, width: int) -> str:
        text = cls.to_zengin_charset(value)
        encoded = text.encode(ENCODING)[:width]
        return encoded.decode(ENCODING, errors="ignore").ljust(width)

    @staticmethod
    def _number(value: str, width: int, *, label: str) -> str:
        digits = value.strip()
        if not digits.isdigit():
            raise ValueError(f"{label} must be digits: '{value}'")
        if len(digits) > width:
            raise ValueError(f"{label} must be at most {width} digits: '{value}'")
        return digits.rjust(width, "0")

    @staticmethod
    def _amount(value: Decimal, width: int) -> str:
        if value != value.to_integral_value():
            raise ValueError("transfer amount must be an integer yen value")
        digits = str(int(value))
        if len(digits) > width:
            raise ValueError(f"transfer amount exceeds {width} digits: {value}")
        return digits.rjust(width, "0")

    @classmethod
    def _account_type(cls, value: str) -> str:
        if value not in _ACCOUNT_TYPES:
            raise ValueError(f"unknown account_type: '{value}'")
        return value

    @classmethod
    def _header(cls, request: TransferRequest) -> str:
        return "".join(
            (
                RECORD_TYPE_HEADER,
                CATEGORY_CODE_TRANSFER,
                CHAR_CODE_JIS,
                cls._number(request.consignor_code, 10, label="consignor_code"),
                cls._text(request.consignor_name, 40),
                f"{request.transfer_date.month:02d}{request.transfer_date.day:02d}",
                cls._number(request.bank_code, 4, label="bank_code"),
                cls._text(request.bank_name, 15),
                cls._number(request.branch_code, 3, label="branch_code"),
                cls._text(request.branch_name, 15),
                cls._account_type(request.account_type),
                cls._number(request.account_number, 7, label="account_number"),
                " " * 17,
            )
        )

    @classmethod
    def _data(cls, line: TransferLine, transfer_amount: Decimal) -> str:
        return "".join(
            (
                RECORD_TYPE_DATA,
                cls._number(line.bank_code, 4, label="bank_code"),
                cls._text(line.bank_name, 15),
                cls._number(line.branch_code, 3, label="branch_code"),
                cls._text(line.branch_name, 15),
                " " * 4,
                cls._account_type(line.account_type),
                cls._number(line.account_number, 7, label="account_number"),
                cls._text(line.recipient_name, 30),
                cls._amount(transfer_amount, 10),
                NEW_CODE_OTHER,
                cls._text(line.customer_code, 10),
                " " * 10,
                TRANSFER_METHOD_TELEGRAPHIC,
                " ",
                " " * 7,
            )
        )

    @classmethod
    def _trailer(cls, detail_count: int, total_amount: Decimal) -> str:
        return "".join(
            (
                RECORD_TYPE_TRAILER,
                str(detail_count).rjust(6, "0"),
                cls._amount(total_amount, 12),
                " " * 101,
            )
        )

    @classmethod
    def _end(cls) -> str:
        return RECORD_TYPE_END + " " * 119

    @classmethod
    def generate(cls, request: TransferRequest) -> ZenginTransferResult:
        if not request.lines:
            raise ValueError("at least one transfer line is required")
        if len(request.lines) > 999999:
            raise ValueError("too many transfer lines")

        records: list[str] = [cls._header(request)]
        line_results: list[TransferLineResult] = []
        total_amount = _ZERO
        total_fee = _ZERO

        for line in request.lines:
            if line.amount <= _ZERO:
                raise ValueError(f"amount must be positive: {line.recipient_name}")
            if line.transfer_fee < _ZERO:
                raise ValueError(f"transfer_fee must not be negative: {line.recipient_name}")
            fee = line.transfer_fee if line.fee_borne_by_recipient else _ZERO
            transfer_amount = line.amount - fee
            if transfer_amount <= _ZERO:
                raise ValueError(
                    f"transfer_fee exceeds amount: {line.recipient_name}"
                )
            records.append(cls._data(line, transfer_amount))
            line_results.append(
                TransferLineResult(
                    recipient_name=cls.to_zengin_charset(line.recipient_name),
                    payable_amount=line.amount,
                    transfer_fee=line.transfer_fee,
                    transfer_amount=transfer_amount,
                    fee_borne_by_recipient=line.fee_borne_by_recipient,
                ),
            )
            total_amount += transfer_amount
            total_fee += fee

        records.append(cls._trailer(len(request.lines), total_amount))
        records.append(cls._end())

        for record in records:
            encoded = record.encode(ENCODING)
            if len(encoded) != RECORD_LENGTH:
                raise ValueError(
                    f"generated record is {len(encoded)} bytes, expected {RECORD_LENGTH}"
                )

        return ZenginTransferResult(
            records=records,
            detail_count=len(request.lines),
            total_amount=total_amount,
            total_fee_deducted=total_fee,
            lines=line_results,
            encoding=ENCODING,
            record_length=RECORD_LENGTH,
        )

    @classmethod
    def encode(cls, result: ZenginTransferResult) -> bytes:
        return b"\r\n".join(record.encode(ENCODING) for record in result.records) + b"\r\n"
