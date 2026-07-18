"""短時間労働者の社会保険 適用拡大判定(健保法3条・厚年法12条、2024年10月〜)。

通常の労働者は、週所定労働時間および月所定労働日数が通常の労働者の4分の3以上で
あれば被保険者となる(4分の3基準)。これを満たさない短時間労働者でも、次の要件を
すべて満たし、かつ特定適用事業所に使用される場合は被保険者となる(適用拡大)。

短時間労働者の要件(すべて満たす):
  1. 週の所定労働時間が20時間以上
  2. 所定内賃金が月額88,000円以上
  3. 2か月を超えて雇用される見込みがある
  4. 学生でない

特定適用事業所:
  - 厚生年金保険の被保険者数が51人以上(2024年10月〜)
  - 50人以下でも、労使合意に基づく任意特定適用事業所であれば対象
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

WEEKLY_HOURS_THRESHOLD = Decimal("20")
MONTHLY_WAGE_THRESHOLD = Decimal("88000")
SPECIFIED_WORKPLACE_THRESHOLD = 51  # 2024年10月〜


@dataclass(frozen=True)
class ShortTimeInsuranceResult:
    covered: bool
    is_specified_workplace: bool
    meets_hours: bool
    meets_wage: bool
    meets_employment_period: bool
    not_student: bool
    reasons: tuple[str, ...]


class ShortTimeWorkerInsuranceService:
    """短時間労働者の社会保険 適用拡大の判定を行う純粋サービス。"""

    @classmethod
    def judge(
        cls,
        *,
        weekly_hours: Decimal,
        monthly_wage: Decimal,
        employment_over_2_months: bool,
        is_student: bool,
        company_insured_count: int,
        labor_agreement: bool = False,
        meets_three_quarters_standard: bool = False,
        specified_workplace_threshold: int = SPECIFIED_WORKPLACE_THRESHOLD,
    ) -> ShortTimeInsuranceResult:
        if weekly_hours < 0:
            raise ValueError("weekly_hours must not be negative")
        if monthly_wage < 0:
            raise ValueError("monthly_wage must not be negative")
        if company_insured_count < 0:
            raise ValueError("company_insured_count must not be negative")

        meets_hours = weekly_hours >= WEEKLY_HOURS_THRESHOLD
        meets_wage = monthly_wage >= MONTHLY_WAGE_THRESHOLD
        meets_employment_period = employment_over_2_months
        not_student = not is_student
        is_specified_workplace = company_insured_count >= specified_workplace_threshold or labor_agreement

        # 4分の3基準を満たせば適用拡大の判定を要さず被保険者。
        if meets_three_quarters_standard:
            return ShortTimeInsuranceResult(
                covered=True,
                is_specified_workplace=is_specified_workplace,
                meets_hours=meets_hours,
                meets_wage=meets_wage,
                meets_employment_period=meets_employment_period,
                not_student=not_student,
                reasons=(),
            )

        reasons: list[str] = []
        if not is_specified_workplace:
            reasons.append("特定適用事業所でない")
        if not meets_hours:
            reasons.append("週所定労働時間が20時間未満")
        if not meets_wage:
            reasons.append("月額賃金が88,000円未満")
        if not meets_employment_period:
            reasons.append("2か月を超える雇用見込みがない")
        if not not_student:
            reasons.append("学生である")

        covered = not reasons
        return ShortTimeInsuranceResult(
            covered=covered,
            is_specified_workplace=is_specified_workplace,
            meets_hours=meets_hours,
            meets_wage=meets_wage,
            meets_employment_period=meets_employment_period,
            not_student=not_student,
            reasons=tuple(reasons),
        )
