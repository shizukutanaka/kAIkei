from decimal import Decimal

from app.services.financial_kpi import FinancialKpiService


def test_basic_ratios():
    kpis = FinancialKpiService.compute(
        revenue=Decimal("1000"),
        expense=Decimal("600"),
        assets=Decimal("2000"),
        liabilities=Decimal("800"),
        equity=Decimal("1200"),
    )
    assert kpis.net_income == Decimal("400")
    assert kpis.net_profit_margin == Decimal("0.4000")
    assert kpis.expense_ratio == Decimal("0.6000")
    assert kpis.equity_ratio == Decimal("0.6000")
    assert kpis.debt_ratio == Decimal("0.6667")  # 800/1200 rounded half-up
    assert kpis.return_on_assets == Decimal("0.2000")


def test_zero_denominators_return_none():
    kpis = FinancialKpiService.compute(
        revenue=Decimal("0"),
        expense=Decimal("0"),
        assets=Decimal("0"),
        liabilities=Decimal("0"),
        equity=Decimal("0"),
    )
    assert kpis.net_income == Decimal("0")
    assert kpis.net_profit_margin is None
    assert kpis.expense_ratio is None
    assert kpis.equity_ratio is None
    assert kpis.debt_ratio is None
    assert kpis.return_on_assets is None


def test_loss_yields_negative_margin():
    kpis = FinancialKpiService.compute(
        revenue=Decimal("500"),
        expense=Decimal("800"),
        assets=Decimal("1000"),
        liabilities=Decimal("600"),
        equity=Decimal("400"),
    )
    assert kpis.net_income == Decimal("-300")
    assert kpis.net_profit_margin == Decimal("-0.6000")
    assert kpis.return_on_assets == Decimal("-0.3000")
