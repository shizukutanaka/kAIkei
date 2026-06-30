from decimal import ROUND_HALF_UP, Decimal


class BudgetService:
    """予算管理エンジン — 予算実績差異（バジェット vs アクチュアル）を算出する。"""

    @staticmethod
    def actual_from_balance(debit_total: Decimal, credit_total: Decimal, normal_balance: str) -> Decimal:
        """月次残高（借方/貸方合計）から、科目の正常残高に応じた実績純額を算出する。

        費用・資産（借方科目）: debit - credit
        収益・負債・純資産（貸方科目）: credit - debit
        """
        if normal_balance == "credit":
            return credit_total - debit_total
        return debit_total - credit_total

    @staticmethod
    def line_variance(budgeted: Decimal, actual: Decimal) -> dict[str, Decimal | bool]:
        """1明細の差異を算出する。

        - variance_amount: 実績 - 予算（正なら予算超過）
        - variance_rate: 差異率(%) = variance_amount / |予算| * 100（予算0なら0）
        - execution_rate: 予算消化率(%) = 実績 / 予算 * 100（予算0なら0）
        - is_over_budget: 実績が予算を上回るか
        """
        variance_amount = actual - budgeted
        if budgeted == 0:
            variance_rate = Decimal("0")
            execution_rate = Decimal("0")
        else:
            variance_rate = (variance_amount / abs(budgeted) * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            execution_rate = (actual / budgeted * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return {
            "budgeted_amount": budgeted,
            "actual_amount": actual,
            "variance_amount": variance_amount,
            "variance_rate": variance_rate,
            "execution_rate": execution_rate,
            "is_over_budget": actual > budgeted,
        }

    @staticmethod
    def summarize(lines: list[dict[str, Decimal | bool]]) -> dict[str, Decimal | int]:
        """明細差異のリストを集計する。"""
        budgeted_total = sum((Decimal(str(line["budgeted_amount"])) for line in lines), Decimal("0"))
        actual_total = sum((Decimal(str(line["actual_amount"])) for line in lines), Decimal("0"))
        variance_total = actual_total - budgeted_total
        over_budget_count = sum(1 for line in lines if line["is_over_budget"])
        if budgeted_total == 0:
            execution_rate = Decimal("0")
        else:
            execution_rate = (actual_total / budgeted_total * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return {
            "budgeted_total": budgeted_total,
            "actual_total": actual_total,
            "variance_total": variance_total,
            "execution_rate": execution_rate,
            "over_budget_count": over_budget_count,
            "line_count": len(lines),
        }
