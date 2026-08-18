from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# 労働基準法37条 / 割増賃金の法定倍率
# 月60時間を境に割増率が上がる（この時間数までが1.25倍、超過分は1.5倍）。
OVERTIME_MONTHLY_THRESHOLD_HOURS = Decimal("60")
OVERTIME_RATE_WITHIN_60_HOURS = Decimal("1.25")
OVERTIME_RATE_OVER_60_HOURS = Decimal("1.50")
LATE_NIGHT_RATE_ADDON = Decimal("0.25")
HOLIDAY_RATE = Decimal("1.35")


@dataclass(frozen=True)
class OvertimePayResult:
    overtime_pay: Decimal
    overtime_over_60_pay: Decimal
    late_night_pay: Decimal
    holiday_pay: Decimal
    total_premium: Decimal


class OvertimePayService:
    @staticmethod
    def _calc(hourly_wage: Decimal, hours: Decimal, multiplier: Decimal) -> Decimal:
        return (hourly_wage * hours * multiplier).quantize(Decimal("1"), rounding=ROUND_DOWN)

    @classmethod
    def compute(
        cls,
        hourly_wage: Decimal,
        overtime_hours: Decimal = Decimal("0"),
        overtime_over_60_hours: Decimal = Decimal("0"),
        late_night_hours: Decimal = Decimal("0"),
        holiday_hours: Decimal = Decimal("0"),
    ) -> OvertimePayResult:
        if hourly_wage < 0:
            raise ValueError("hourly_wage must be non-negative")
        if overtime_hours < 0 or overtime_over_60_hours < 0 or late_night_hours < 0 or holiday_hours < 0:
            raise ValueError("hours must be non-negative")

        overtime_pay = cls._calc(hourly_wage, overtime_hours, OVERTIME_RATE_WITHIN_60_HOURS)
        overtime_over_60_pay = cls._calc(hourly_wage, overtime_over_60_hours, OVERTIME_RATE_OVER_60_HOURS)
        late_night_pay = cls._calc(hourly_wage, late_night_hours, LATE_NIGHT_RATE_ADDON)
        holiday_pay = cls._calc(hourly_wage, holiday_hours, HOLIDAY_RATE)
        total_premium = overtime_pay + overtime_over_60_pay + late_night_pay + holiday_pay
        return OvertimePayResult(
            overtime_pay=overtime_pay,
            overtime_over_60_pay=overtime_over_60_pay,
            late_night_pay=late_night_pay,
            holiday_pay=holiday_pay,
            total_premium=total_premium,
        )
