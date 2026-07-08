"""適格請求書発行事業者登録番号（インボイス登録番号）の検証（純粋ロジック）。

登録番号は「T」+ 13桁の数字。13桁が法人番号の場合はチェックディジットで整合性を検証できる
（法人番号法・国税庁仕様）。個人事業者に付番される番号は法人番号ではないため、
チェックディジット検証は法人番号に対してのみ有効である点に注意。

法人番号チェックディジット:
    検査用数字 = 9 - ( ( Σ[n=1..12] Pn × Qn ) を 9 で除した余り )
      Pn: 基礎番号（下位12桁）の各桁。最下位を n=1 とする。
      Qn: n が奇数のとき 1、偶数のとき 2。
    先頭1桁が検査用数字、続く12桁が基礎番号。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_REGISTRATION_RE = re.compile(r"^T(\d{13})$")


@dataclass(frozen=True)
class RegistrationNumberCheck:
    input: str
    normalized: str | None
    format_valid: bool
    check_digit_valid: bool


def _compute_corporate_check_digit(digits13: str) -> int:
    base = digits13[1:]  # 下位12桁（基礎番号）
    total = 0
    for i, char in enumerate(reversed(base)):  # i=0 が最下位 -> n=i+1
        n = i + 1
        weight = 1 if n % 2 == 1 else 2
        total += int(char) * weight
    return 9 - (total % 9)


class InvoiceRegistrationService:
    """登録番号の形式・チェックディジットを検証する純粋サービス。"""

    @staticmethod
    def normalize(raw: str) -> str:
        """空白・ハイフンを除去し大文字化する。"""
        return re.sub(r"[\s\-]", "", raw).upper()

    @classmethod
    def validate(cls, raw: str) -> RegistrationNumberCheck:
        normalized = cls.normalize(raw)
        match = _REGISTRATION_RE.match(normalized)
        if match is None:
            return RegistrationNumberCheck(
                input=raw, normalized=None, format_valid=False, check_digit_valid=False
            )
        digits13 = match.group(1)
        expected = _compute_corporate_check_digit(digits13)
        check_digit_valid = int(digits13[0]) == expected
        return RegistrationNumberCheck(
            input=raw,
            normalized=normalized,
            format_valid=True,
            check_digit_valid=check_digit_valid,
        )
