"""通勤手当の非課税限度額の判定。

所得税法9条1項5号 / 所得税法施行令20条の2: 通勤手当のうち一定額までは非課税。
- 交通機関等を利用: その運賃等の額（1か月あたり150,000円が上限）。
- マイカー・自転車等: 片道通勤距離に応じた月額の非課税限度額。
（令和6年分の限度額）
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

MODE_TRANSIT = "transit"
MODE_CAR = "car"

# 交通機関等利用者の1か月あたり非課税限度額
TRANSIT_MONTHLY_LIMIT = Decimal("150000")

# マイカー・自転車等 片道通勤距離(km)別の1か月あたり非課税限度額
# (下限km以上・次の下限km未満) → 非課税限度額
CAR_DISTANCE_LIMITS: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal("55"), Decimal("31600")),
    (Decimal("45"), Decimal("28000")),
    (Decimal("35"), Decimal("24400")),
    (Decimal("25"), Decimal("18700")),
    (Decimal("15"), Decimal("12900")),
    (Decimal("10"), Decimal("7100")),
    (Decimal("2"), Decimal("4200")),
    (Decimal("0"), Decimal("0")),  # 片道2km未満は全額課税
)


@dataclass(frozen=True)
class CommuteAllowanceResult:
    mode: str
    monthly_allowance: Decimal
    non_taxable_limit: Decimal
    non_taxable: Decimal
    taxable: Decimal


class CommuteAllowanceService:
    @staticmethod
    def _car_limit(one_way_distance_km: Decimal) -> Decimal:
        if one_way_distance_km < 0:
            raise ValueError("one_way_distance_km must be non-negative")
        for lower, limit in CAR_DISTANCE_LIMITS:
            if one_way_distance_km >= lower:
                return limit
        return Decimal("0")

    @classmethod
    def compute(
        cls,
        mode: str,
        monthly_allowance: Decimal,
        one_way_distance_km: Decimal | None = None,
    ) -> CommuteAllowanceResult:
        if monthly_allowance < 0:
            raise ValueError("monthly_allowance must be non-negative")

        if mode == MODE_TRANSIT:
            limit = TRANSIT_MONTHLY_LIMIT
        elif mode == MODE_CAR:
            if one_way_distance_km is None:
                raise ValueError("one_way_distance_km is required for car mode")
            limit = cls._car_limit(one_way_distance_km)
        else:
            raise ValueError(f"unsupported mode: {mode}")

        non_taxable = monthly_allowance if monthly_allowance <= limit else limit
        taxable = monthly_allowance - non_taxable
        return CommuteAllowanceResult(
            mode=mode,
            monthly_allowance=monthly_allowance,
            non_taxable_limit=limit,
            non_taxable=non_taxable,
            taxable=taxable,
        )
