"""退職所得の源泉徴収税額の計算。

所得税法30条・201条: 退職手当等については退職所得控除を控除し、原則としてその2分の1を
課税退職所得金額として分離課税(速算表)により所得税額を求め、復興特別所得税(2.1%)を加算する。
- 退職所得控除: 勤続20年以下は40万円×年数(最低80万円)、20年超は800万円+70万円×(年数−20)。
  勤続年数の1年未満は切上げ。
- 特定役員退職手当等(役員等で勤続5年以下)は2分の1課税の適用なし。
- 短期退職手当等(役員等以外で勤続5年以下)は控除後300万円超の部分に2分の1課税を適用しない。
- 「退職所得の受給に関する申告書」未提出の場合は退職手当等の額×20.42%(分離)。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from app.services.income_tax import IncomeTaxService

DEDUCTION_PER_YEAR_UP_TO_20 = Decimal("400000")
DEDUCTION_MIN = Decimal("800000")
DEDUCTION_BASE_OVER_20 = Decimal("8000000")
DEDUCTION_PER_YEAR_OVER_20 = Decimal("700000")
SHORT_TERM_HALF_CAP_BASE = Decimal("3000000")
SHORT_TERM_HALF_AMOUNT = Decimal("1500000")
RECONSTRUCTION_MULTIPLIER = Decimal("1.021")
NO_STATEMENT_RATE = Decimal("0.2042")


@dataclass(frozen=True)
class RetirementIncomeTaxResult:
    years_of_service: int
    retirement_income_deduction: Decimal
    taxable_base: Decimal
    taxable_retirement_income: Decimal
    income_tax_base: Decimal
    statement_submitted: bool
    withholding_tax: Decimal


class RetirementIncomeTaxService:
    @staticmethod
    def _years(months_of_service: int) -> int:
        years = -(-months_of_service // 12)  # ceil division
        return max(years, 1)

    @classmethod
    def _deduction(cls, years: int) -> Decimal:
        if years <= 20:
            return max(DEDUCTION_PER_YEAR_UP_TO_20 * Decimal(years), DEDUCTION_MIN)
        return DEDUCTION_BASE_OVER_20 + DEDUCTION_PER_YEAR_OVER_20 * Decimal(years - 20)

    @classmethod
    def compute(
        cls,
        severance_pay: Decimal,
        months_of_service: int,
        is_specified_officer_5yr_or_less: bool = False,
        is_short_term_5yr_or_less: bool = False,
        statement_submitted: bool = True,
    ) -> RetirementIncomeTaxResult:
        if severance_pay < 0:
            raise ValueError("severance_pay must be non-negative")
        if months_of_service < 0:
            raise ValueError("months_of_service must be non-negative")
        if is_specified_officer_5yr_or_less and is_short_term_5yr_or_less:
            raise ValueError("cannot be both specified officer and short-term")

        years = cls._years(months_of_service)
        if (is_specified_officer_5yr_or_less or is_short_term_5yr_or_less) and years > 5:
            raise ValueError("5-year rule flags require years_of_service <= 5")

        deduction = cls._deduction(years)

        if not statement_submitted:
            withholding = (severance_pay * NO_STATEMENT_RATE).quantize(Decimal("1"), rounding=ROUND_DOWN)
            return RetirementIncomeTaxResult(
                years_of_service=years,
                retirement_income_deduction=deduction,
                taxable_base=Decimal("0"),
                taxable_retirement_income=Decimal("0"),
                income_tax_base=Decimal("0"),
                statement_submitted=False,
                withholding_tax=withholding,
            )

        taxable_base = severance_pay - deduction
        if taxable_base < 0:
            taxable_base = Decimal("0")

        if is_specified_officer_5yr_or_less:
            taxable_income = taxable_base
        elif is_short_term_5yr_or_less and taxable_base > SHORT_TERM_HALF_CAP_BASE:
            taxable_income = SHORT_TERM_HALF_AMOUNT + (taxable_base - SHORT_TERM_HALF_CAP_BASE)
        else:
            taxable_income = taxable_base / Decimal("2")

        income_tax_base = IncomeTaxService.compute(taxable_income)
        withholding = (income_tax_base * RECONSTRUCTION_MULTIPLIER).quantize(Decimal("1"), rounding=ROUND_DOWN)

        return RetirementIncomeTaxResult(
            years_of_service=years,
            retirement_income_deduction=deduction,
            taxable_base=taxable_base,
            taxable_retirement_income=taxable_income,
            income_tax_base=income_tax_base,
            statement_submitted=True,
            withholding_tax=withholding,
        )
