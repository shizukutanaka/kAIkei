"""適格請求書発行事業者番号（インボイス登録番号）の検証。

登録番号は "T" + 13桁の法人番号（または個人事業者向けの13桁数字）で構成される。
先頭の1桁は検査用数字（チェックディジット）で、残り12桁の基礎番号から国税庁の
アルゴリズムで算出される。ローカルで書式・検査用数字を検証し、入力ミスを弾く。

（実在確認は国税庁「適格請求書発行事業者公表システム Web-API」で別途行う。）
"""
import re

_NORMALIZE = re.compile(r"[\s\-‐－]")
_FORMAT = re.compile(r"^T\d{13}$")


def normalize(number: str | None) -> str:
    """空白・ハイフンを除去し大文字化する。"""
    if not number:
        return ""
    return _NORMALIZE.sub("", number).upper()


def compute_check_digit(base12: str) -> int:
    """12桁の基礎番号から検査用数字（0〜9）を算出する（国税庁方式）。

    検査用数字 = 9 − ( Σ P_n × Q_n ) mod 9
      P_n: 基礎番号を下1桁目から数えたn桁目の値
      Q_n: nが奇数なら1、偶数なら2
    """
    if len(base12) != 12 or not base12.isdigit():
        raise ValueError("base12 must be 12 digits")
    total = 0
    for n, ch in enumerate(reversed(base12), start=1):
        q = 1 if n % 2 == 1 else 2
        total += int(ch) * q
    return 9 - (total % 9)


def is_valid_corporate_number(number13: str) -> bool:
    """13桁の法人番号の検査用数字を検証する。"""
    if len(number13) != 13 or not number13.isdigit():
        return False
    check = int(number13[0])
    base12 = number13[1:]
    return check == compute_check_digit(base12)


def is_valid_registration_number(number: str | None) -> bool:
    """インボイス登録番号（T+13桁）の書式と検査用数字を検証する。"""
    normalized = normalize(number)
    if not _FORMAT.match(normalized):
        return False
    return is_valid_corporate_number(normalized[1:])
