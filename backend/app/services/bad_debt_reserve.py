"""貸倒引当金 繰入限度額の計算(法人税法52条・租税特別措置法57条の9、一括評価)。

中小法人等は、期末の一括評価金銭債権(売掛金・貸付金等)の帳簿価額に法定繰入率を
乗じた額まで貸倒引当金の繰入れを損金算入できる。

一括評価による繰入限度額:
    (期末一括評価金銭債権 − 実質的に債権とみられない金額) × 法定繰入率

法定繰入率(業種別、参考値。改正で変動しうるため引数で上書き可能):
    卸売業・小売業        : 10 / 1000
    製造業                :  8 / 1000
    金融業・保険業        :  3 / 1000
    割賦販売小売業等      :  7 / 1000
    その他               :  6 / 1000

「実質的に債権とみられない金額」は、同一取引先に対する買掛金等と相殺可能な額を除く
趣旨で、控除額として入力する。繰入限度額は円未満切捨。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

INDUSTRY_WHOLESALE_RETAIL = "wholesale_retail"
INDUSTRY_MANUFACTURING = "manufacturing"
INDUSTRY_FINANCE_INSURANCE = "finance_insurance"
INDUSTRY_INSTALLMENT_RETAIL = "installment_retail"
INDUSTRY_OTHER = "other"

STATUTORY_RATES = {
    INDUSTRY_WHOLESALE_RETAIL: Decimal("0.010"),
    INDUSTRY_MANUFACTURING: Decimal("0.008"),
    INDUSTRY_FINANCE_INSURANCE: Decimal("0.003"),
    INDUSTRY_INSTALLMENT_RETAIL: Decimal("0.007"),
    INDUSTRY_OTHER: Decimal("0.006"),
}


@dataclass(frozen=True)
class BadDebtReserveResult:
    statutory_rate: Decimal
    base_amount: Decimal
    reserve_limit: Decimal


class BadDebtReserveService:
    """一括評価による貸倒引当金の繰入限度額を算定する純粋サービス。"""

    @staticmethod
    def compute(
        *,
        receivables: Decimal,
        industry: str,
        non_receivable_amount: Decimal = Decimal("0"),
        statutory_rate: Decimal | None = None,
    ) -> BadDebtReserveResult:
        if receivables < 0:
            raise ValueError("receivables must not be negative")
        if non_receivable_amount < 0:
            raise ValueError("non_receivable_amount must not be negative")

        if statutory_rate is None:
            if industry not in STATUTORY_RATES:
                raise ValueError(f"無効な業種: {industry}")
            rate = STATUTORY_RATES[industry]
        else:
            if statutory_rate <= 0:
                raise ValueError("statutory_rate must be positive")
            rate = statutory_rate

        base = receivables - non_receivable_amount
        if base < 0:
            base = Decimal("0")

        reserve_limit = (base * rate).quantize(Decimal("1"), rounding=ROUND_DOWN)

        return BadDebtReserveResult(
            statutory_rate=rate,
            base_amount=base,
            reserve_limit=reserve_limit,
        )
