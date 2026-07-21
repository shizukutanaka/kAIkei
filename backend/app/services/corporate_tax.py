"""法人税額の計算(法人税法66条・租税特別措置法42条の3の2、中小法人の軽減税率)。

普通法人の法人税率は原則23.2%。ただし資本金1億円以下等の中小法人については、
所得のうち年800万円以下の部分に軽減税率が適用される。

軽減税率(年800万円以下の部分):
    中小法人(原則)              : 15%(措置法の特例税率)
    適用除外事業者(過去3年平均所得15億円超): 19%
    年800万円超の部分・大法人   : 23.2%

計算手順:
    1. 課税所得金額の千円未満を切り捨てる。
    2. 軽減税率の適用上限(年800万円)を事業年度の月数で按分する
       (800万円 × 事業年度の月数 ÷ 12)。
    3. 上限以下の部分に軽減税率、超過部分に23.2%を適用する。
    4. 法人税額の百円未満を切り捨てる。

税率・上限は改正されうるため、既定値は現行(参考)値とし引数で上書き可能。
地方法人税・法人住民税・事業税は含まない(別途)。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

STANDARD_RATE = Decimal("0.232")
REDUCED_RATE_SMALL = Decimal("0.15")
REDUCED_RATE_EXCLUDED = Decimal("0.19")
REDUCED_BRACKET_ANNUAL = Decimal("8000000")


@dataclass(frozen=True)
class CorporateTaxResult:
    rounded_income: Decimal
    reduced_rate: Decimal
    reduced_bracket: Decimal
    reduced_tax: Decimal
    standard_tax: Decimal
    total_tax: Decimal


class CorporateTaxService:
    """法人税額を算定する純粋サービス。"""

    @staticmethod
    def compute(
        *,
        taxable_income: Decimal,
        months: int = 12,
        small_business: bool = True,
        excluded_business: bool = False,
        standard_rate: Decimal = STANDARD_RATE,
    ) -> CorporateTaxResult:
        if taxable_income < 0:
            raise ValueError("taxable_income must not be negative")
        if months <= 0 or months > 12:
            raise ValueError("months must be between 1 and 12")

        rounded_income = (taxable_income // Decimal("1000")) * Decimal("1000")

        if small_business:
            reduced_rate = (
                REDUCED_RATE_EXCLUDED if excluded_business else REDUCED_RATE_SMALL
            )
            reduced_bracket = (
                REDUCED_BRACKET_ANNUAL * Decimal(months) / Decimal("12")
            ).quantize(Decimal("1"), rounding=ROUND_DOWN)
        else:
            reduced_rate = standard_rate
            reduced_bracket = Decimal("0")

        reduced_base = min(rounded_income, reduced_bracket)
        standard_base = rounded_income - reduced_base

        reduced_tax = reduced_base * reduced_rate
        standard_tax = standard_base * standard_rate

        total_tax = ((reduced_tax + standard_tax) // Decimal("100")) * Decimal("100")

        return CorporateTaxResult(
            rounded_income=rounded_income,
            reduced_rate=reduced_rate,
            reduced_bracket=reduced_bracket,
            reduced_tax=reduced_tax.quantize(Decimal("1"), rounding=ROUND_DOWN),
            standard_tax=standard_tax.quantize(Decimal("1"), rounding=ROUND_DOWN),
            total_tax=total_tax,
        )
