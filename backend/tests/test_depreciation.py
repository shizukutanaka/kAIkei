from decimal import Decimal

import pytest

from app.services.depreciation import DepreciationService


class TestDepreciationService:
    def test_period_amount_matches_formula(self):
        acquisition_cost = Decimal("1200000")
        salvage_value = Decimal("100000")
        useful_life_months = 10
        accumulated = Decimal("200000")

        expected_monthly = (acquisition_cost - salvage_value) / Decimal(useful_life_months)

        assert DepreciationService.period_amount(
            acquisition_cost,
            salvage_value,
            useful_life_months,
            accumulated,
        ) == expected_monthly

    def test_period_amount_clamps_to_remaining_base(self):
        acquisition_cost = Decimal("1200000")
        salvage_value = Decimal("100000")
        useful_life_months = 10
        accumulated = Decimal("1090000")

        assert DepreciationService.period_amount(
            acquisition_cost,
            salvage_value,
            useful_life_months,
            accumulated,
        ) == Decimal("10000")

    def test_straight_line_schedule_full_and_partial(self):
        acquisition_cost = Decimal("1300000")
        salvage_value = Decimal("100000")
        useful_life_months = 12

        full_schedule = DepreciationService.straight_line_schedule(
            acquisition_cost,
            salvage_value,
            useful_life_months,
        )
        assert len(full_schedule) == useful_life_months
        assert full_schedule[-1].accumulated == acquisition_cost - salvage_value
        assert full_schedule[-1].book_value == salvage_value
        assert sum(entry.depreciation for entry in full_schedule) == acquisition_cost - salvage_value
        assert [entry.accumulated for entry in full_schedule] == sorted(entry.accumulated for entry in full_schedule)

        partial_schedule = DepreciationService.straight_line_schedule(
            acquisition_cost,
            salvage_value,
            useful_life_months,
            accumulated_depreciation=Decimal("300000"),
        )
        assert len(partial_schedule) == 9
        assert partial_schedule[-1].accumulated == acquisition_cost - salvage_value
        assert partial_schedule[-1].book_value == salvage_value
        assert sum(entry.depreciation for entry in partial_schedule) == (acquisition_cost - salvage_value) - Decimal("300000")

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            DepreciationService.straight_line_schedule(
                Decimal("100000"),
                Decimal("0"),
                0,
            )
        with pytest.raises(ValueError):
            DepreciationService.straight_line_schedule(
                Decimal("100000"),
                Decimal("200000"),
                12,
            )
