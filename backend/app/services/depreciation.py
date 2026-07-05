from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DepreciationScheduleEntry:
    period_index: int
    depreciation: Decimal
    accumulated: Decimal
    book_value: Decimal


class DepreciationService:
    @staticmethod
    def _validate_inputs(
        acquisition_cost: Decimal,
        salvage_value: Decimal,
        useful_life_months: int,
        accumulated_depreciation: Decimal,
    ) -> Decimal:
        if useful_life_months <= 0:
            raise ValueError("useful_life_months must be positive")
        if acquisition_cost < 0:
            raise ValueError("acquisition_cost must be non-negative")
        if salvage_value < 0:
            raise ValueError("salvage_value must be non-negative")
        if salvage_value > acquisition_cost:
            raise ValueError("salvage_value must not exceed acquisition_cost")
        if accumulated_depreciation < 0:
            raise ValueError("accumulated_depreciation must be non-negative")

        depreciable_base = acquisition_cost - salvage_value
        if accumulated_depreciation > depreciable_base:
            raise ValueError("accumulated_depreciation must not exceed depreciable_base")
        return depreciable_base

    @classmethod
    def period_amount(
        cls,
        acquisition_cost: Decimal,
        salvage_value: Decimal,
        useful_life_months: int,
        accumulated_depreciation: Decimal,
    ) -> Decimal:
        depreciable_base = cls._validate_inputs(
            acquisition_cost,
            salvage_value,
            useful_life_months,
            accumulated_depreciation,
        )
        monthly_depreciation = depreciable_base / Decimal(useful_life_months)
        remaining = depreciable_base - accumulated_depreciation
        return monthly_depreciation if monthly_depreciation <= remaining else remaining

    @classmethod
    def straight_line_schedule(
        cls,
        acquisition_cost: Decimal,
        salvage_value: Decimal,
        useful_life_months: int,
        accumulated_depreciation: Decimal = Decimal("0"),
    ) -> list[DepreciationScheduleEntry]:
        depreciable_base = cls._validate_inputs(
            acquisition_cost,
            salvage_value,
            useful_life_months,
            accumulated_depreciation,
        )
        monthly_depreciation = depreciable_base / Decimal(useful_life_months)

        schedule: list[DepreciationScheduleEntry] = []
        current_accumulated = accumulated_depreciation
        period_index = 1
        while current_accumulated < depreciable_base:
            remaining = depreciable_base - current_accumulated
            depreciation = monthly_depreciation if monthly_depreciation <= remaining else remaining
            current_accumulated += depreciation
            schedule.append(
                DepreciationScheduleEntry(
                    period_index=period_index,
                    depreciation=depreciation,
                    accumulated=current_accumulated,
                    book_value=acquisition_cost - current_accumulated,
                )
            )
            period_index += 1
        return schedule
