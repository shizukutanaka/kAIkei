"""法人事業税(所得割)の計算(地方税法72条の24の7、標準税率)。

資本金1億円以下の普通法人(外形標準課税の対象外)については、所得を課税標準とする
所得割が課される。標準税率は所得の区分に応じた3段階(軽減税率適用法人)。

標準税率(令和元年10月1日以後開始事業年度):
    年400万円以下の部分        : 3.5%
    年400万円超800万円以下の部分: 5.3%
    年800万円超の部分          : 7.0%

計算手順:
    1. 課税標準(所得)の千円未満を切り捨てる。
    2. 軽減税率適用区分(年400万・800万)を事業年度の月数で按分する。
    3. 区分ごとに標準税率を適用して合算する。
    4. 事業税額の百円未満を切り捨てる。

税率・区分は改正され、また超過税率を条例で定める自治体があるため、既定値は標準税率の
参考値とし引数で上書き可能。地方法人特別税/特別法人事業税・法人住民税は含まない。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

RATE_LOW = Decimal("0.035")
RATE_MIDDLE = Decimal("0.053")
RATE_HIGH = Decimal("0.070")
BRACKET_LOW_ANNUAL = Decimal("4000000")
BRACKET_MIDDLE_ANNUAL = Decimal("8000000")


@dataclass(frozen=True)
class BusinessTaxResult:
    rounded_income: Decimal
    low_base: Decimal
    middle_base: Decimal
    high_base: Decimal
    tax_amount: Decimal


class BusinessTaxService:
    """法人事業税(所得割)を算定する純粋サービス。"""

    @staticmethod
    def compute(
        *,
        taxable_income: Decimal,
        months: int = 12,
        rate_low: Decimal = RATE_LOW,
        rate_middle: Decimal = RATE_MIDDLE,
        rate_high: Decimal = RATE_HIGH,
    ) -> BusinessTaxResult:
        if taxable_income < 0:
            raise ValueError("taxable_income must not be negative")
        if months <= 0 or months > 12:
            raise ValueError("months must be between 1 and 12")

        rounded_income = (taxable_income // Decimal("1000")) * Decimal("1000")

        bracket_low = (
            BRACKET_LOW_ANNUAL * Decimal(months) / Decimal("12")
        ).quantize(Decimal("1"), rounding=ROUND_DOWN)
        bracket_middle = (
            BRACKET_MIDDLE_ANNUAL * Decimal(months) / Decimal("12")
        ).quantize(Decimal("1"), rounding=ROUND_DOWN)

        low_base = min(rounded_income, bracket_low)
        middle_base = min(max(rounded_income - bracket_low, Decimal("0")), bracket_middle - bracket_low)
        high_base = max(rounded_income - bracket_middle, Decimal("0"))

        raw_tax = low_base * rate_low + middle_base * rate_middle + high_base * rate_high
        tax_amount = (raw_tax // Decimal("100")) * Decimal("100")

        return BusinessTaxResult(
            rounded_income=rounded_income,
            low_base=low_base,
            middle_base=middle_base,
            high_base=high_base,
            tax_amount=tax_amount,
        )
