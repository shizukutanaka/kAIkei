from decimal import ROUND_DOWN, Decimal

from app.services.tax_forecast import EFFECTIVE_CORPORATE_TAX_RATE, TaxForecastService


class TestTaxForecastService:
    def test_positive_profit_forecast_and_floor_tax(self):
        result = TaxForecastService.forecast(
            total_revenue=Decimal("1000"),
            total_expense=Decimal("400"),
            forecast_factor=Decimal("1.2"),
        )

        assert result.forecasted_profit_before_tax == Decimal("720.0")
        assert result.estimated_taxable_income == Decimal("720.0")
        assert result.estimated_tax_amount == (
            Decimal("720.0") * EFFECTIVE_CORPORATE_TAX_RATE
        ).quantize(Decimal("1"), rounding=ROUND_DOWN)
        assert result.tax_risk_warnings == []

    def test_loss_results_in_zero_tax_and_red_warning(self):
        result = TaxForecastService.forecast(
            total_revenue=Decimal("300"),
            total_expense=Decimal("500"),
            forecast_factor=Decimal("1.0"),
        )

        assert result.forecasted_profit_before_tax == Decimal("-200.0")
        assert result.estimated_taxable_income == Decimal("0")
        assert result.estimated_tax_amount == Decimal("0")
        assert result.tax_risk_warnings == ["赤字着地の見込みです。"]

    def test_large_forecast_factor_warns_on_extrapolation(self):
        result = TaxForecastService.forecast(
            total_revenue=Decimal("1000"),
            total_expense=Decimal("100"),
            forecast_factor=Decimal("1.6"),
        )

        assert result.tax_risk_warnings == ["年間換算係数が大きく、予測精度に注意が必要です。"]
