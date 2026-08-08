"""年次有給休暇の付与日数の算定。

労働基準法39条: 雇入れの日から6か月継続勤務し全労働日の8割以上出勤した労働者に
10労働日を付与し、以後継続勤務年数に応じて加算する。週所定労働日数が4日以下かつ
週所定労働時間が30時間未満の労働者には所定労働日数に応じた比例付与を行う。
付与日数が10日以上の労働者には、年5日の時季指定義務(労基法39条7項)が生じる。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# 8割以上出勤要件
ATTENDANCE_REQUIREMENT = Decimal("0.8")
# 通常の労働者の判定閾値
FULL_TIME_WEEKLY_HOURS = 30
FULL_TIME_WEEKLY_DAYS = 5
# 年5日の時季指定義務が生じる付与日数
MANDATORY_DESIGNATION_THRESHOLD = 10

# 継続勤務6か月・1年6か月・…・6年6か月以上（7区分）
# 通常の労働者
FULL_TIME_GRANT = (10, 11, 12, 14, 16, 18, 20)
# 比例付与（週所定労働日数別）
PROPORTIONAL_GRANT: dict[int, tuple[int, ...]] = {
    4: (7, 8, 9, 10, 12, 13, 15),
    3: (5, 6, 6, 8, 9, 10, 11),
    2: (3, 4, 4, 5, 6, 6, 7),
    1: (1, 2, 2, 2, 3, 3, 3),
}


@dataclass(frozen=True)
class PaidLeaveResult:
    granted_days: int
    is_proportional: bool
    meets_attendance_requirement: bool
    mandatory_5day_designation: bool


class PaidLeaveService:
    @staticmethod
    def _service_index(months_of_service: int) -> int | None:
        if months_of_service < 6:
            return None
        return min((months_of_service - 6) // 12, 6)

    @classmethod
    def grant_days(
        cls,
        months_of_service: int,
        weekly_working_days: int,
        weekly_working_hours: Decimal,
        attendance_rate: Decimal,
    ) -> PaidLeaveResult:
        if months_of_service < 0:
            raise ValueError("months_of_service must be non-negative")
        if weekly_working_days < 0 or weekly_working_days > 7:
            raise ValueError("weekly_working_days must be between 0 and 7")
        if weekly_working_hours < 0:
            raise ValueError("weekly_working_hours must be non-negative")
        if attendance_rate < 0 or attendance_rate > 1:
            raise ValueError("attendance_rate must be between 0 and 1")

        is_full_time = weekly_working_hours >= FULL_TIME_WEEKLY_HOURS or weekly_working_days >= FULL_TIME_WEEKLY_DAYS
        index = cls._service_index(months_of_service)
        meets_attendance = attendance_rate >= ATTENDANCE_REQUIREMENT

        if index is None or not meets_attendance:
            granted = 0
        elif is_full_time:
            granted = FULL_TIME_GRANT[index]
        else:
            table = PROPORTIONAL_GRANT.get(weekly_working_days)
            granted = table[index] if table is not None else 0

        return PaidLeaveResult(
            granted_days=granted,
            is_proportional=not is_full_time,
            meets_attendance_requirement=meets_attendance,
            mandatory_5day_designation=granted >= MANDATORY_DESIGNATION_THRESHOLD,
        )
