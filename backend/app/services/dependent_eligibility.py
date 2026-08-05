"""健康保険の被扶養者(収入要件)の認定判定。

健康保険法3条7項・認定基準(昭52保発9号等):
- 年間収入が130万円未満(認定対象者が60歳以上または障害者の場合は180万円未満)であること。
- かつ同一世帯の場合は被保険者の年間収入の2分の1未満、別居の場合は被保険者からの
  援助(仕送り)額より少ないこと。
いずれも「向こう1年間の見込み収入」で判定する。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

INCOME_LIMIT_STANDARD = Decimal("1300000")
INCOME_LIMIT_SENIOR_OR_DISABLED = Decimal("1800000")


@dataclass(frozen=True)
class DependentEligibilityResult:
    income_limit: Decimal
    income_requirement_met: bool
    relationship_requirement_met: bool
    eligible: bool
    reason: str


class DependentEligibilityService:
    @classmethod
    def check(
        cls,
        annual_income: Decimal,
        is_senior_or_disabled: bool = False,
        cohabiting: bool = True,
        insured_annual_income: Decimal | None = None,
        remittance_amount: Decimal | None = None,
    ) -> DependentEligibilityResult:
        if annual_income < 0:
            raise ValueError("annual_income must be non-negative")

        limit = INCOME_LIMIT_SENIOR_OR_DISABLED if is_senior_or_disabled else INCOME_LIMIT_STANDARD
        income_ok = annual_income < limit

        if cohabiting:
            if insured_annual_income is None:
                raise ValueError("insured_annual_income is required when cohabiting")
            if insured_annual_income < 0:
                raise ValueError("insured_annual_income must be non-negative")
            relationship_ok = annual_income < insured_annual_income / Decimal("2")
        else:
            if remittance_amount is None:
                raise ValueError("remittance_amount is required when not cohabiting")
            if remittance_amount < 0:
                raise ValueError("remittance_amount must be non-negative")
            relationship_ok = annual_income < remittance_amount

        eligible = income_ok and relationship_ok
        if eligible:
            reason = "eligible"
        elif not income_ok:
            reason = "annual_income_over_limit"
        else:
            reason = "cohabiting_half_income_failed" if cohabiting else "remittance_requirement_failed"

        return DependentEligibilityResult(
            income_limit=limit,
            income_requirement_met=income_ok,
            relationship_requirement_met=relationship_ok,
            eligible=eligible,
            reason=reason,
        )
