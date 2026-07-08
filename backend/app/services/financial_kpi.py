"""経営ダッシュボード向け財務KPI算出（純粋ロジック）。

勘定科目区分（account_type: revenue/expense/asset/liability/equity）の集計値のみから
導出できる比率に限定する。流動/固定の内訳など勘定科目体系に依存する指標は、会社ごとの
分類が必要なためここでは扱わない。分母が0の指標は None を返す（未定義）。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_ZERO = Decimal("0")
_QUANT = Decimal("0.0001")


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == _ZERO:
        return None
    return (numerator / denominator).quantize(_QUANT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FinancialKpis:
    net_income: Decimal
    net_profit_margin: Decimal | None
    expense_ratio: Decimal | None
    equity_ratio: Decimal | None
    debt_ratio: Decimal | None
    return_on_assets: Decimal | None


class FinancialKpiService:
    """財務集計値から経営KPIを決定論的に算出する純粋サービス。"""

    @staticmethod
    def compute(
        *,
        revenue: Decimal,
        expense: Decimal,
        assets: Decimal,
        liabilities: Decimal,
        equity: Decimal,
    ) -> FinancialKpis:
        net_income = revenue - expense
        return FinancialKpis(
            net_income=net_income,
            net_profit_margin=_ratio(net_income, revenue),
            expense_ratio=_ratio(expense, revenue),
            equity_ratio=_ratio(equity, assets),
            debt_ratio=_ratio(liabilities, equity),
            return_on_assets=_ratio(net_income, assets),
        )
