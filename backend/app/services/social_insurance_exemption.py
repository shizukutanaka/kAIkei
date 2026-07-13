"""産前産後休業・育児休業中の社会保険料免除の判定。

健康保険法159条・159条の3 / 厚生年金保険法81条の2・81条の2の2:
- 産前産後休業・育児休業等の期間中は、事業主の申出により被保険者・事業主とも保険料が免除される。
- 月次保険料: その月の末日が休業期間中である場合に当月分を免除。育児休業については
  令和4年10月改正により、同一月内に14日以上の育児休業を取得した場合も当月分を免除。
- 賞与保険料: 育児休業は賞与月の末日を含んで連続1か月超の休業を取得した場合に免除
  (令和4年10月改正)。産前産後休業は末日が休業期間中であれば免除。
"""

from __future__ import annotations

from dataclasses import dataclass

LEAVE_MATERNITY = "maternity"
LEAVE_CHILDCARE = "childcare"
TARGET_MONTHLY = "monthly"
TARGET_BONUS = "bonus"

CHILDCARE_MONTHLY_DAYS_THRESHOLD = 14


@dataclass(frozen=True)
class SocialInsuranceExemptionResult:
    exempt: bool
    reason: str


class SocialInsuranceExemptionService:
    @classmethod
    def check(
        cls,
        leave_type: str,
        target: str,
        month_last_day_on_leave: bool = False,
        days_on_leave_in_month: int = 0,
        continuous_leave_over_one_month: bool = False,
    ) -> SocialInsuranceExemptionResult:
        if leave_type not in (LEAVE_MATERNITY, LEAVE_CHILDCARE):
            raise ValueError(f"unsupported leave_type: {leave_type}")
        if target not in (TARGET_MONTHLY, TARGET_BONUS):
            raise ValueError(f"unsupported target: {target}")
        if days_on_leave_in_month < 0:
            raise ValueError("days_on_leave_in_month must be non-negative")

        if leave_type == LEAVE_MATERNITY:
            if month_last_day_on_leave:
                return SocialInsuranceExemptionResult(True, "maternity_month_end_on_leave")
            return SocialInsuranceExemptionResult(False, "maternity_not_on_month_end")

        if target == TARGET_MONTHLY:
            if month_last_day_on_leave:
                return SocialInsuranceExemptionResult(True, "childcare_month_end_on_leave")
            if days_on_leave_in_month >= CHILDCARE_MONTHLY_DAYS_THRESHOLD:
                return SocialInsuranceExemptionResult(True, "childcare_14_days_or_more")
            return SocialInsuranceExemptionResult(False, "childcare_monthly_not_exempt")

        if continuous_leave_over_one_month:
            return SocialInsuranceExemptionResult(True, "childcare_continuous_over_one_month")
        return SocialInsuranceExemptionResult(False, "childcare_bonus_not_over_one_month")
