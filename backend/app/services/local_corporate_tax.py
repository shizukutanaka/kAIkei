"""地方法人税の計算(地方法人税法)。

地方法人税は、各課税事業年度の基準法人税額(≒法人税額)を課税標準として国が課す
国税で、税率は10.3%。法人住民税・事業税(地方税)とは別。

計算手順:
    1. 課税標準法人税額(基準法人税額)の千円未満を切り捨てる。
    2. 課税標準法人税額 × 税率(10.3%) を算出する。
    3. 地方法人税額の百円未満を切り捨てる。

税率は改正されうるため既定値は現行(参考)値とし、引数で上書き可能。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

STANDARD_RATE = Decimal("0.103")


@dataclass(frozen=True)
class LocalCorporateTaxResult:
    tax_base: Decimal
    rate: Decimal
    tax_amount: Decimal


class LocalCorporateTaxService:
    """地方法人税額を算定する純粋サービス。"""

    @staticmethod
    def compute(
        *,
        corporate_tax_amount: Decimal,
        rate: Decimal = STANDARD_RATE,
    ) -> LocalCorporateTaxResult:
        if corporate_tax_amount < 0:
            raise ValueError("corporate_tax_amount must not be negative")
        if rate <= 0:
            raise ValueError("rate must be positive")

        tax_base = (corporate_tax_amount // Decimal("1000")) * Decimal("1000")
        tax_amount = ((tax_base * rate) // Decimal("100")) * Decimal("100")

        return LocalCorporateTaxResult(
            tax_base=tax_base,
            rate=rate,
            tax_amount=tax_amount,
        )
