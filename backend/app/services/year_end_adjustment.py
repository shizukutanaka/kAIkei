"""年末調整の年税額・過不足額(還付/追徴)の精算。

所得税法190条〜192条: 給与の支払者は、その年最後の給与の支払時に年間の給与所得について
年税額を計算し、毎月徴収した源泉徴収税額の合計との過不足を精算する。
- 給与所得 = 年間給与収入 − 給与所得控除。
- 課税給与所得金額 = 給与所得 − 所得控除合計(1,000円未満切捨は速算表側で処理)。
- 算出所得税額に住宅借入金等特別控除(税額控除)を差し引いて年調所得税額を求め、
  復興特別所得税(2.1%)を加算し100円未満を切り捨てて年調年税額とする。
- 年調年税額 < 徴収済 → 還付、年調年税額 > 徴収済 → 追徴。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from app.services.income_tax import IncomeTaxService
from app.services.salary_deduction import SalaryIncomeDeductionService

RECONSTRUCTION_MULTIPLIER = Decimal("1.021")
YEAR_TAX_ROUNDING_UNIT = Decimal("100")


@dataclass(frozen=True)
class YearEndAdjustmentResult:
    salary_income_deduction: Decimal
    salary_income: Decimal
    taxable_income: Decimal
    calculated_income_tax: Decimal
    housing_loan_credit: Decimal
    year_adjusted_income_tax: Decimal
    year_tax: Decimal
    withheld_tax_total: Decimal
    refund: Decimal
    additional_collection: Decimal


class YearEndAdjustmentService:
    @staticmethod
    def _floor_to_unit(amount: Decimal, unit: Decimal) -> Decimal:
        return (amount // unit) * unit

    @classmethod
    def compute(
        cls,
        annual_gross_salary: Decimal,
        total_income_deductions: Decimal,
        withheld_tax_total: Decimal,
        housing_loan_credit: Decimal = Decimal("0"),
    ) -> YearEndAdjustmentResult:
        for name, value in (
            ("annual_gross_salary", annual_gross_salary),
            ("total_income_deductions", total_income_deductions),
            ("withheld_tax_total", withheld_tax_total),
            ("housing_loan_credit", housing_loan_credit),
        ):
            if value < 0:
                raise ValueError(f"{name} must be non-negative")

        salary_income_deduction = SalaryIncomeDeductionService.compute(annual_gross_salary)
        salary_income = annual_gross_salary - salary_income_deduction

        taxable_income = salary_income - total_income_deductions
        if taxable_income < 0:
            taxable_income = Decimal("0")

        calculated_income_tax = IncomeTaxService.compute(taxable_income)
        year_adjusted_income_tax = calculated_income_tax - housing_loan_credit
        if year_adjusted_income_tax < 0:
            year_adjusted_income_tax = Decimal("0")

        year_tax = cls._floor_to_unit(
            (year_adjusted_income_tax * RECONSTRUCTION_MULTIPLIER).quantize(Decimal("1"), rounding=ROUND_DOWN),
            YEAR_TAX_ROUNDING_UNIT,
        )

        difference = withheld_tax_total - year_tax
        refund = difference if difference > 0 else Decimal("0")
        additional_collection = -difference if difference < 0 else Decimal("0")

        return YearEndAdjustmentResult(
            salary_income_deduction=salary_income_deduction,
            salary_income=salary_income,
            taxable_income=taxable_income,
            calculated_income_tax=calculated_income_tax,
            housing_loan_credit=housing_loan_credit,
            year_adjusted_income_tax=year_adjusted_income_tax,
            year_tax=year_tax,
            withheld_tax_total=withheld_tax_total,
            refund=refund,
            additional_collection=additional_collection,
        )
