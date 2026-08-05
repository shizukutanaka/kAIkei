"""労災保険 休業(補償)給付の支給額計算(労働者災害補償保険法14条)。

業務災害・通勤災害により労働できず賃金を受けられない場合、待期3日を経過した
4日目以降について支給される。

支給額(1日あたり):
  休業(補償)給付   = 給付基礎日額 × 60%
  休業特別支給金     = 給付基礎日額 × 20%
  合計               = 給付基礎日額 × 80% 相当

待期期間:
  - 通算3日間は待期(業務災害の場合、事業主が労基法76条の休業補償を行う)。
  - waiting_completed=True の場合は待期を経過済みとして全日を支給対象とする。

一部労働した日(所定労働時間の一部を労働):
  - 給付基礎日額から実際に支払われた賃金を控除した額を基礎に算定する。
    休業(補償)給付 = (給付基礎日額 − 支払賃金) × 60%

給付基礎日額には年齢階層別の最高限度額・最低保障額(年度改定)があるが、
本サービスは確定した給付基礎日額を入力として受け取る。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

WAITING_DAYS = 3
COMPENSATION_RATE = Decimal("0.60")
SPECIAL_RATE = Decimal("0.20")


@dataclass(frozen=True)
class WorkersAccidentLeaveResult:
    payable_days: int
    daily_compensation: Decimal
    daily_special: Decimal
    total_compensation: Decimal
    total_special: Decimal
    total_benefit: Decimal


class WorkersAccidentLeaveService:
    """労災 休業(補償)給付の支給額を算定する純粋サービス。"""

    @staticmethod
    def compute(
        *,
        daily_wage_base: Decimal,
        absent_days: int,
        waiting_completed: bool = False,
        daily_partial_wage: Decimal = Decimal("0"),
    ) -> WorkersAccidentLeaveResult:
        if daily_wage_base <= 0:
            raise ValueError("daily_wage_base must be positive")
        if absent_days < 0:
            raise ValueError("absent_days must not be negative")
        if daily_partial_wage < 0:
            raise ValueError("daily_partial_wage must not be negative")

        base = daily_wage_base - daily_partial_wage
        if base < 0:
            base = Decimal("0")

        daily_compensation = (base * COMPENSATION_RATE).quantize(
            Decimal("1"), rounding=ROUND_DOWN
        )
        daily_special = (base * SPECIAL_RATE).quantize(
            Decimal("1"), rounding=ROUND_DOWN
        )

        payable_days = (
            absent_days if waiting_completed else max(absent_days - WAITING_DAYS, 0)
        )

        total_compensation = daily_compensation * payable_days
        total_special = daily_special * payable_days

        return WorkersAccidentLeaveResult(
            payable_days=payable_days,
            daily_compensation=daily_compensation,
            daily_special=daily_special,
            total_compensation=total_compensation,
            total_special=total_special,
            total_benefit=total_compensation + total_special,
        )
