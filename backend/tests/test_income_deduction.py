"""基礎控除・扶養控除の額。

年末調整のエンドポイントが所得控除を一切引かずに給与収入へ税率を掛けていたため、
税額が実際の数倍になっていた。控除額の決定を各所で組み立て直すと同じことが
起きるので、ここに集約した分を検証する。
"""
from decimal import Decimal

import pytest

from app.services.income_deduction import basic_deduction, dependent_deduction


@pytest.mark.parametrize(
    ("total_income", "expected"),
    [
        (Decimal("0"), Decimal("480000")),
        (Decimal("5000000"), Decimal("480000")),
        # 2,400万円ちょうどまでは満額
        (Decimal("24000000"), Decimal("480000")),
        (Decimal("24000001"), Decimal("320000")),
        (Decimal("24500000"), Decimal("320000")),
        (Decimal("24500001"), Decimal("160000")),
        (Decimal("25000000"), Decimal("160000")),
        # 2,500万円超で0
        (Decimal("25000001"), Decimal("0")),
        (Decimal("100000000"), Decimal("0")),
    ],
)
def test_basic_deduction_tiers(total_income, expected):
    """所得税法86条の逓減。境界は「以下」で切り替わる。"""
    assert basic_deduction(total_income) == expected


def test_basic_deduction_rejects_negative():
    with pytest.raises(ValueError):
        basic_deduction(Decimal("-1"))


@pytest.mark.parametrize(
    ("dependents", "expected"),
    [(0, Decimal("0")), (1, Decimal("380000")), (3, Decimal("1140000"))],
)
def test_dependent_deduction(dependents, expected):
    assert dependent_deduction(dependents) == expected


def test_dependent_deduction_rejects_negative():
    with pytest.raises(ValueError):
        dependent_deduction(-1)


class TestStandardBonus:
    """標準賞与額（1,000円未満切捨・法定上限）。

    賞与額に率を直接掛けていた旧実装では、切り捨ても上限も効かず、
    高額賞与で保険料を過大に徴収していた。
    """

    def test_floors_to_1000_yen(self):
        from app.services.social_insurance import standard_bonus_amounts

        result = standard_bonus_amounts(Decimal("500999"))
        assert result.health == Decimal("500000")
        assert result.pension == Decimal("500000")

    def test_pension_is_capped_per_payment(self):
        """厚生年金は1回につき150万円が上限（厚年法24条の4）。"""
        from app.services.social_insurance import (
            PENSION_STANDARD_BONUS_PER_PAYMENT_CAP,
            standard_bonus_amounts,
        )

        result = standard_bonus_amounts(Decimal("2000000"))
        assert result.pension == PENSION_STANDARD_BONUS_PER_PAYMENT_CAP
        # 健康保険側は1回あたりの上限が無いので、そのまま。
        assert result.health == Decimal("2000000")

    def test_health_is_capped_by_the_annual_total(self):
        """健康保険は年度累計573万円が上限（健保法40条2項）。"""
        from app.services.social_insurance import standard_bonus_amounts

        result = standard_bonus_amounts(Decimal("1000000"), Decimal("5500000"))
        assert result.health == Decimal("230000"), "年度の残枠までに制限されていない"

    def test_health_is_zero_once_the_annual_cap_is_reached(self):
        from app.services.social_insurance import standard_bonus_amounts

        result = standard_bonus_amounts(Decimal("1000000"), Decimal("5730000"))
        assert result.health == Decimal("0")
        assert result.pension == Decimal("1000000"), "厚生年金は年度上限の影響を受けない"

    def test_rejects_negative(self):
        from app.services.social_insurance import standard_bonus_amounts

        with pytest.raises(ValueError):
            standard_bonus_amounts(Decimal("-1"))
