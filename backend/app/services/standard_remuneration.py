
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# 厚生年金保険 標準報酬月額等級表（令和2年9月分以降・32等級）
PENSION_GRADE_TABLE: tuple[tuple[int, Decimal, Decimal, Decimal | None], ...] = (
    (1, Decimal("88000"), Decimal("0"), Decimal("93000")),
    (2, Decimal("98000"), Decimal("93000"), Decimal("101000")),
    (3, Decimal("104000"), Decimal("101000"), Decimal("107000")),
    (4, Decimal("110000"), Decimal("107000"), Decimal("114000")),
    (5, Decimal("118000"), Decimal("114000"), Decimal("122000")),
    (6, Decimal("126000"), Decimal("122000"), Decimal("130000")),
    (7, Decimal("134000"), Decimal("130000"), Decimal("138000")),
    (8, Decimal("142000"), Decimal("138000"), Decimal("146000")),
    (9, Decimal("150000"), Decimal("146000"), Decimal("155000")),
    (10, Decimal("160000"), Decimal("155000"), Decimal("165000")),
    (11, Decimal("170000"), Decimal("165000"), Decimal("175000")),
    (12, Decimal("180000"), Decimal("175000"), Decimal("185000")),
    (13, Decimal("190000"), Decimal("185000"), Decimal("195000")),
    (14, Decimal("200000"), Decimal("195000"), Decimal("210000")),
    (15, Decimal("220000"), Decimal("210000"), Decimal("230000")),
    (16, Decimal("240000"), Decimal("230000"), Decimal("250000")),
    (17, Decimal("260000"), Decimal("250000"), Decimal("270000")),
    (18, Decimal("280000"), Decimal("270000"), Decimal("290000")),
    (19, Decimal("300000"), Decimal("290000"), Decimal("310000")),
    (20, Decimal("320000"), Decimal("310000"), Decimal("330000")),
    (21, Decimal("340000"), Decimal("330000"), Decimal("350000")),
    (22, Decimal("360000"), Decimal("350000"), Decimal("370000")),
    (23, Decimal("380000"), Decimal("370000"), Decimal("395000")),
    (24, Decimal("410000"), Decimal("395000"), Decimal("425000")),
    (25, Decimal("440000"), Decimal("425000"), Decimal("455000")),
    (26, Decimal("470000"), Decimal("455000"), Decimal("485000")),
    (27, Decimal("500000"), Decimal("485000"), Decimal("515000")),
    (28, Decimal("530000"), Decimal("515000"), Decimal("545000")),
    (29, Decimal("560000"), Decimal("545000"), Decimal("575000")),
    (30, Decimal("590000"), Decimal("575000"), Decimal("605000")),
    (31, Decimal("620000"), Decimal("605000"), Decimal("635000")),
    (32, Decimal("650000"), Decimal("635000"), None),
)

# 協会けんぽ 健康保険 標準報酬月額等級表（令和6年度・50等級）
HEALTH_GRADE_TABLE: tuple[tuple[int, Decimal, Decimal, Decimal | None], ...] = (
    (1, Decimal("58000"), Decimal("0"), Decimal("63000")),
    (2, Decimal("68000"), Decimal("63000"), Decimal("73000")),
    (3, Decimal("78000"), Decimal("73000"), Decimal("83000")),
    (4, Decimal("88000"), Decimal("83000"), Decimal("93000")),
    (5, Decimal("98000"), Decimal("93000"), Decimal("101000")),
    (6, Decimal("104000"), Decimal("101000"), Decimal("107000")),
    (7, Decimal("110000"), Decimal("107000"), Decimal("114000")),
    (8, Decimal("118000"), Decimal("114000"), Decimal("122000")),
    (9, Decimal("126000"), Decimal("122000"), Decimal("130000")),
    (10, Decimal("134000"), Decimal("130000"), Decimal("138000")),
    (11, Decimal("142000"), Decimal("138000"), Decimal("146000")),
    (12, Decimal("150000"), Decimal("146000"), Decimal("155000")),
    (13, Decimal("160000"), Decimal("155000"), Decimal("165000")),
    (14, Decimal("170000"), Decimal("165000"), Decimal("175000")),
    (15, Decimal("180000"), Decimal("175000"), Decimal("185000")),
    (16, Decimal("190000"), Decimal("185000"), Decimal("195000")),
    (17, Decimal("200000"), Decimal("195000"), Decimal("210000")),
    (18, Decimal("220000"), Decimal("210000"), Decimal("230000")),
    (19, Decimal("240000"), Decimal("230000"), Decimal("250000")),
    (20, Decimal("260000"), Decimal("250000"), Decimal("270000")),
    (21, Decimal("280000"), Decimal("270000"), Decimal("290000")),
    (22, Decimal("300000"), Decimal("290000"), Decimal("310000")),
    (23, Decimal("320000"), Decimal("310000"), Decimal("330000")),
    (24, Decimal("340000"), Decimal("330000"), Decimal("350000")),
    (25, Decimal("360000"), Decimal("350000"), Decimal("370000")),
    (26, Decimal("380000"), Decimal("370000"), Decimal("395000")),
    (27, Decimal("410000"), Decimal("395000"), Decimal("425000")),
    (28, Decimal("440000"), Decimal("425000"), Decimal("455000")),
    (29, Decimal("470000"), Decimal("455000"), Decimal("485000")),
    (30, Decimal("500000"), Decimal("485000"), Decimal("515000")),
    (31, Decimal("530000"), Decimal("515000"), Decimal("545000")),
    (32, Decimal("560000"), Decimal("545000"), Decimal("575000")),
    (33, Decimal("590000"), Decimal("575000"), Decimal("605000")),
    (34, Decimal("620000"), Decimal("605000"), Decimal("635000")),
    (35, Decimal("650000"), Decimal("635000"), Decimal("665000")),
    (36, Decimal("680000"), Decimal("665000"), Decimal("695000")),
    (37, Decimal("710000"), Decimal("695000"), Decimal("730000")),
    (38, Decimal("750000"), Decimal("730000"), Decimal("770000")),
    (39, Decimal("790000"), Decimal("770000"), Decimal("810000")),
    (40, Decimal("830000"), Decimal("810000"), Decimal("855000")),
    (41, Decimal("880000"), Decimal("855000"), Decimal("905000")),
    (42, Decimal("930000"), Decimal("905000"), Decimal("955000")),
    (43, Decimal("980000"), Decimal("955000"), Decimal("1005000")),
    (44, Decimal("1030000"), Decimal("1005000"), Decimal("1055000")),
    (45, Decimal("1090000"), Decimal("1055000"), Decimal("1115000")),
    (46, Decimal("1150000"), Decimal("1115000"), Decimal("1175000")),
    (47, Decimal("1210000"), Decimal("1175000"), Decimal("1235000")),
    (48, Decimal("1270000"), Decimal("1235000"), Decimal("1295000")),
    (49, Decimal("1330000"), Decimal("1295000"), Decimal("1355000")),
    (50, Decimal("1390000"), Decimal("1355000"), None),
)


@dataclass(frozen=True)
class RemunerationMonth:
    payment_basis_days: int
    remuneration: Decimal


@dataclass(frozen=True)
class GradeResult:
    grade: int
    standard_monthly_remuneration: Decimal


class StandardRemunerationService:
    @staticmethod
    def determine_remuneration_monthly(
        months: list[RemunerationMonth],
        min_payment_basis_days: int = 17,
    ) -> Decimal | None:
        if not months:
            raise ValueError("months must not be empty")
        if min_payment_basis_days < 0:
            raise ValueError("min_payment_basis_days must be non-negative")

        qualifying: list[Decimal] = []
        for month in months:
            if month.payment_basis_days < 0 or month.remuneration < 0:
                raise ValueError("months must be non-negative")
            if month.payment_basis_days >= min_payment_basis_days:
                qualifying.append(month.remuneration)

        if not qualifying:
            return None

        average = sum(qualifying, Decimal("0")) / Decimal(len(qualifying))
        return average.quantize(Decimal("1"), rounding=ROUND_DOWN)

    @staticmethod
    def _lookup_grade(remuneration: Decimal, grade_table: tuple[tuple[int, Decimal, Decimal, Decimal | None], ...]) -> GradeResult:
        if remuneration < 0:
            raise ValueError("remuneration must be non-negative")

        for grade, standard_monthly_remuneration, lower_bound, upper_bound_exclusive in grade_table:
            if remuneration < lower_bound:
                continue
            if upper_bound_exclusive is None or remuneration < upper_bound_exclusive:
                return GradeResult(grade=grade, standard_monthly_remuneration=standard_monthly_remuneration)

        grade, standard_monthly_remuneration, _, _ = grade_table[-1]
        return GradeResult(grade=grade, standard_monthly_remuneration=standard_monthly_remuneration)

    @classmethod
    def lookup_pension_grade(cls, remuneration: Decimal) -> GradeResult:
        return cls._lookup_grade(remuneration, PENSION_GRADE_TABLE)

    @classmethod
    def lookup_health_grade(cls, remuneration: Decimal) -> GradeResult:
        return cls._lookup_grade(remuneration, HEALTH_GRADE_TABLE)
