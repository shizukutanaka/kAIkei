"""所得控除のうち、年末調整で機械的に決まるもの（基礎控除・扶養控除）。

年末調整のエンドポイントが所得控除を一切引かずに「給与収入そのもの」へ税率を
掛けていたため、税額が実際の数倍になっていた。金額を各エンドポイントで
組み立て直すと同じことが起きるので、控除額の決定をここに集約する。

医療費控除・生命保険料控除などの申告性の控除は、金額を利用者から受け取る
必要があるためここでは扱わない（`total_income_deductions` に加算して渡す）。
"""
from __future__ import annotations

from decimal import Decimal

# 所得税法86条 / 基礎控除。合計所得金額に応じて逓減し、2,500万円超で0になる。
BASIC_DEDUCTION_TIERS: tuple[tuple[Decimal | None, Decimal], ...] = (
    (Decimal("24000000"), Decimal("480000")),
    (Decimal("24500000"), Decimal("320000")),
    (Decimal("25000000"), Decimal("160000")),
    (None, Decimal("0")),
)

# 所得税法84条 / 扶養控除（一般の控除対象扶養親族）。
# 特定扶養親族(19〜22歳)63万・老人扶養親族48万/58万は年齢情報が必要なため、
# 現時点では区分を持たず一般として扱う。区分を保持できるようになったら分岐させる。
GENERAL_DEPENDENT_DEDUCTION = Decimal("380000")


def basic_deduction(total_income: Decimal) -> Decimal:
    """合計所得金額に対する基礎控除額。"""
    if total_income < 0:
        raise ValueError("total_income must be non-negative")
    for ceiling, amount in BASIC_DEDUCTION_TIERS:
        if ceiling is None or total_income <= ceiling:
            return amount
    return Decimal("0")  # pragma: no cover -- 最終段が None のため到達しない


def dependent_deduction(dependents: int) -> Decimal:
    """控除対象扶養親族の数に対する扶養控除額（一般のみ）。"""
    if dependents < 0:
        raise ValueError("dependents must be non-negative")
    return GENERAL_DEPENDENT_DEDUCTION * dependents
