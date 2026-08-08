"""高額療養費の自己負担限度額・支給額計算(健康保険法115条、70歳未満)。

同一月・同一医療機関の窓口自己負担額が所得区分別の自己負担限度額を超えた場合、
超えた額が高額療養費として支給される。

所得区分(70歳未満、標準報酬月額ベース)と自己負担限度額:
  ア(標報83万以上)   : 252,600円 + (総医療費 − 842,000円) × 1%
  イ(標報53〜79万)   : 167,400円 + (総医療費 − 558,000円) × 1%
  ウ(標報28〜50万)   :  80,100円 + (総医療費 − 267,000円) × 1%
  エ(標報26万以下)   :  57,600円
  オ(住民税非課税)   :  35,400円

多数回該当(直近12か月間に高額療養費の支給が3回以上あった場合、4回目以降):
  ア:140,100円 / イ:93,000円 / ウ:44,400円 / エ:44,400円 / オ:24,600円

限度額・区分は年度・制度改正で変わりうるため、既定値は現行(参考)値。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

CATEGORY_A = "ア"
CATEGORY_B = "イ"
CATEGORY_C = "ウ"
CATEGORY_D = "エ"
CATEGORY_E = "オ"

VALID_CATEGORIES = (CATEGORY_A, CATEGORY_B, CATEGORY_C, CATEGORY_D, CATEGORY_E)

# 通常の限度額(基礎額, 医療費基準額)。エ・オは定額(医療費基準額なし)。
_TIERED = {
    CATEGORY_A: (Decimal("252600"), Decimal("842000")),
    CATEGORY_B: (Decimal("167400"), Decimal("558000")),
    CATEGORY_C: (Decimal("80100"), Decimal("267000")),
}
_FLAT = {
    CATEGORY_D: Decimal("57600"),
    CATEGORY_E: Decimal("35400"),
}
_RATE_OVER_BASE = Decimal("0.01")

# 多数回該当時の限度額(定額)。
_MULTI_LIMIT = {
    CATEGORY_A: Decimal("140100"),
    CATEGORY_B: Decimal("93000"),
    CATEGORY_C: Decimal("44400"),
    CATEGORY_D: Decimal("44400"),
    CATEGORY_E: Decimal("24600"),
}


@dataclass(frozen=True)
class HighCostMedicalResult:
    self_pay_limit: Decimal
    high_cost_benefit: Decimal


class HighCostMedicalService:
    """高額療養費の自己負担限度額と支給額を算定する純粋サービス。"""

    @staticmethod
    def compute(
        *,
        total_medical_cost: Decimal,
        self_paid: Decimal,
        income_category: str,
        multiple_treatment: bool = False,
    ) -> HighCostMedicalResult:
        if income_category not in VALID_CATEGORIES:
            raise ValueError(f"無効な所得区分: {income_category}")
        if total_medical_cost < 0:
            raise ValueError("total_medical_cost must not be negative")
        if self_paid < 0:
            raise ValueError("self_paid must not be negative")

        if multiple_treatment:
            limit = _MULTI_LIMIT[income_category]
        elif income_category in _FLAT:
            limit = _FLAT[income_category]
        else:
            base, threshold = _TIERED[income_category]
            over = max(total_medical_cost - threshold, Decimal("0"))
            limit = base + (over * _RATE_OVER_BASE).quantize(
                Decimal("1"), rounding=ROUND_DOWN
            )

        benefit = self_paid - limit
        if benefit < 0:
            benefit = Decimal("0")

        return HighCostMedicalResult(
            self_pay_limit=limit,
            high_cost_benefit=benefit,
        )
