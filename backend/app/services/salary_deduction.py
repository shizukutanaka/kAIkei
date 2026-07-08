from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

# 所得税法28条 / 令和2年分以降の給与所得控除の速算表
SALARY_DEDUCTION_FIXED_FLOOR = Decimal("550000")
SALARY_DEDUCTION_CAP = Decimal("1950000")
SALARY_DEDUCTION_THRESHOLD_1 = Decimal("1625000")
SALARY_DEDUCTION_THRESHOLD_2 = Decimal("1800000")
SALARY_DEDUCTION_THRESHOLD_3 = Decimal("3600000")
SALARY_DEDUCTION_THRESHOLD_4 = Decimal("6600000")
SALARY_DEDUCTION_THRESHOLD_5 = Decimal("8500000")
SALARY_DEDUCTION_RATE_1 = Decimal("0.40")
SALARY_DEDUCTION_RATE_2 = Decimal("0.30")
SALARY_DEDUCTION_RATE_3 = Decimal("0.20")
SALARY_DEDUCTION_RATE_4 = Decimal("0.10")
SALARY_DEDUCTION_OFFSET_1 = Decimal("100000")
SALARY_DEDUCTION_OFFSET_2 = Decimal("80000")
SALARY_DEDUCTION_OFFSET_3 = Decimal("440000")
SALARY_DEDUCTION_OFFSET_4 = Decimal("1100000")


class SalaryIncomeDeductionService:
    @staticmethod
    def compute(gross_salary: Decimal) -> Decimal:
        if gross_salary < 0:
            raise ValueError("gross_salary must be non-negative")

        if gross_salary <= SALARY_DEDUCTION_THRESHOLD_1:
            deduction = SALARY_DEDUCTION_FIXED_FLOOR
        elif gross_salary <= SALARY_DEDUCTION_THRESHOLD_2:
            deduction = gross_salary * SALARY_DEDUCTION_RATE_1 - SALARY_DEDUCTION_OFFSET_1
        elif gross_salary <= SALARY_DEDUCTION_THRESHOLD_3:
            deduction = gross_salary * SALARY_DEDUCTION_RATE_2 + SALARY_DEDUCTION_OFFSET_2
        elif gross_salary <= SALARY_DEDUCTION_THRESHOLD_4:
            deduction = gross_salary * SALARY_DEDUCTION_RATE_3 + SALARY_DEDUCTION_OFFSET_3
        elif gross_salary <= SALARY_DEDUCTION_THRESHOLD_5:
            deduction = gross_salary * SALARY_DEDUCTION_RATE_4 + SALARY_DEDUCTION_OFFSET_4
        else:
            deduction = SALARY_DEDUCTION_CAP

        return deduction.quantize(Decimal("1"), rounding=ROUND_DOWN)
