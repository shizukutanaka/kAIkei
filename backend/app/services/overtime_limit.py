"""時間外労働の上限規制(36協定)の適合チェック。

労働基準法36条(平成31年4月〜の上限規制):
- 原則: 時間外労働は月45時間・年360時間以内。
- 特別条項を適用する場合でも次を満たす必要がある:
  - 時間外労働は年720時間以内。
  - 時間外労働+休日労働は単月100時間未満。
  - 時間外労働+休日労働は「2〜6か月平均」で80時間以内。
  - 時間外労働が月45時間を超えられるのは年6回まで。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

MONTHLY_OVERTIME_STANDARD_LIMIT = Decimal("45")
ANNUAL_OVERTIME_LIMIT = Decimal("720")
SINGLE_MONTH_COMBINED_LIMIT = Decimal("100")  # 未満であること
MULTI_MONTH_AVERAGE_LIMIT = Decimal("80")  # 以下であること
OVER_45_MONTHS_LIMIT = 6
MAX_AVERAGING_WINDOW = 6


@dataclass(frozen=True)
class MonthlyOvertime:
    overtime_hours: Decimal
    holiday_work_hours: Decimal = Decimal("0")


@dataclass(frozen=True)
class OvertimeLimitResult:
    annual_overtime_total: Decimal
    annual_limit_exceeded: bool
    months_over_45_count: int
    months_over_45_limit_exceeded: bool
    single_month_combined_exceeded: bool
    multi_month_average_exceeded: bool
    compliant: bool
    violations: tuple[str, ...]


class OvertimeLimitService:
    @classmethod
    def check(cls, months: list[MonthlyOvertime]) -> OvertimeLimitResult:
        if not months:
            raise ValueError("months must not be empty")
        for month in months:
            if month.overtime_hours < 0 or month.holiday_work_hours < 0:
                raise ValueError("hours must be non-negative")

        combined = [m.overtime_hours + m.holiday_work_hours for m in months]

        annual_overtime_total = sum((m.overtime_hours for m in months), Decimal("0"))
        annual_limit_exceeded = annual_overtime_total > ANNUAL_OVERTIME_LIMIT

        months_over_45_count = sum(1 for m in months if m.overtime_hours > MONTHLY_OVERTIME_STANDARD_LIMIT)
        months_over_45_limit_exceeded = months_over_45_count > OVER_45_MONTHS_LIMIT

        single_month_combined_exceeded = any(c >= SINGLE_MONTH_COMBINED_LIMIT for c in combined)

        multi_month_average_exceeded = False
        for window in range(2, MAX_AVERAGING_WINDOW + 1):
            for start in range(0, len(combined) - window + 1):
                total = sum(combined[start : start + window], Decimal("0"))
                if total / Decimal(window) > MULTI_MONTH_AVERAGE_LIMIT:
                    multi_month_average_exceeded = True
                    break
            if multi_month_average_exceeded:
                break

        violations: list[str] = []
        if annual_limit_exceeded:
            violations.append("annual_overtime_over_720")
        if months_over_45_limit_exceeded:
            violations.append("over_45_more_than_6_months")
        if single_month_combined_exceeded:
            violations.append("single_month_combined_100_or_more")
        if multi_month_average_exceeded:
            violations.append("multi_month_average_over_80")

        return OvertimeLimitResult(
            annual_overtime_total=annual_overtime_total,
            annual_limit_exceeded=annual_limit_exceeded,
            months_over_45_count=months_over_45_count,
            months_over_45_limit_exceeded=months_over_45_limit_exceeded,
            single_month_combined_exceeded=single_month_combined_exceeded,
            multi_month_average_exceeded=multi_month_average_exceeded,
            compliant=not violations,
            violations=tuple(violations),
        )
