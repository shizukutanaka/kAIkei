from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# 日本の法人実効税率の目安。MVPでは固定の近似値を使う。
EFFECTIVE_CORPORATE_TAX_RATE = Decimal("0.3042")
DEFAULT_FORECAST_FACTOR = Decimal("1.0")


@dataclass(frozen=True)
class TaxForecastResult:
    forecasted_profit_before_tax: Decimal
    estimated_taxable_income: Decimal
    estimated_tax_amount: Decimal
    tax_risk_warnings: list[str]


class TaxForecastService:
    @staticmethod
    def forecast(
        *,
        total_revenue: Decimal,
        total_expense: Decimal,
        forecast_factor: Decimal,
    ) -> TaxForecastResult:
        current_profit = total_revenue - total_expense
        forecasted_profit_before_tax = current_profit * forecast_factor
        estimated_taxable_income = max(forecasted_profit_before_tax, Decimal("0"))
        estimated_tax_amount = (
            estimated_taxable_income * EFFECTIVE_CORPORATE_TAX_RATE
        ).quantize(Decimal("1"), rounding=ROUND_DOWN)

        warnings: list[str] = []
        if forecasted_profit_before_tax < 0:
            warnings.append("赤字着地の見込みです。")
        if forecast_factor > Decimal("1.5"):
            warnings.append("年間換算係数が大きく、予測精度に注意が必要です。")

        return TaxForecastResult(
            forecasted_profit_before_tax=forecasted_profit_before_tax,
            estimated_taxable_income=estimated_taxable_income,
            estimated_tax_amount=estimated_tax_amount,
            tax_risk_warnings=warnings,
        )
