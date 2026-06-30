from decimal import Decimal

from app.services.budget_service import BudgetService


class TestActualFromBalance:
    def test_debit_account(self):
        # 費用・資産（借方科目）: 実績 = 借方 - 貸方
        assert BudgetService.actual_from_balance(Decimal("8000"), Decimal("500"), "debit") == Decimal("7500")

    def test_credit_account(self):
        # 収益（貸方科目）: 実績 = 貸方 - 借方
        assert BudgetService.actual_from_balance(Decimal("1000"), Decimal("12000"), "credit") == Decimal("11000")


class TestLineVariance:
    def test_under_budget(self):
        v = BudgetService.line_variance(Decimal("10000"), Decimal("8000"))
        assert v["variance_amount"] == Decimal("-2000")
        assert v["variance_rate"] == Decimal("-20.00")
        assert v["execution_rate"] == Decimal("80.00")
        assert v["is_over_budget"] is False

    def test_over_budget(self):
        v = BudgetService.line_variance(Decimal("10000"), Decimal("12500"))
        assert v["variance_amount"] == Decimal("2500")
        assert v["variance_rate"] == Decimal("25.00")
        assert v["execution_rate"] == Decimal("125.00")
        assert v["is_over_budget"] is True

    def test_exact(self):
        v = BudgetService.line_variance(Decimal("5000"), Decimal("5000"))
        assert v["variance_amount"] == Decimal("0")
        assert v["execution_rate"] == Decimal("100.00")
        assert v["is_over_budget"] is False

    def test_zero_budget(self):
        v = BudgetService.line_variance(Decimal("0"), Decimal("3000"))
        assert v["variance_amount"] == Decimal("3000")
        assert v["variance_rate"] == Decimal("0")
        assert v["execution_rate"] == Decimal("0")
        assert v["is_over_budget"] is True

    def test_rounding(self):
        v = BudgetService.line_variance(Decimal("3000"), Decimal("1000"))
        # -2000 / 3000 * 100 = -66.666... -> -66.67
        assert v["variance_rate"] == Decimal("-66.67")
        assert v["execution_rate"] == Decimal("33.33")


class TestSummarize:
    def test_summary(self):
        lines = [
            BudgetService.line_variance(Decimal("10000"), Decimal("12000")),
            BudgetService.line_variance(Decimal("5000"), Decimal("4000")),
            BudgetService.line_variance(Decimal("5000"), Decimal("5000")),
        ]
        summary = BudgetService.summarize(lines)
        assert summary["budgeted_total"] == Decimal("20000")
        assert summary["actual_total"] == Decimal("21000")
        assert summary["variance_total"] == Decimal("1000")
        assert summary["execution_rate"] == Decimal("105.00")
        assert summary["over_budget_count"] == 1
        assert summary["line_count"] == 3

    def test_empty(self):
        summary = BudgetService.summarize([])
        assert summary["budgeted_total"] == Decimal("0")
        assert summary["actual_total"] == Decimal("0")
        assert summary["variance_total"] == Decimal("0")
        assert summary["execution_rate"] == Decimal("0")
        assert summary["over_budget_count"] == 0
        assert summary["line_count"] == 0
