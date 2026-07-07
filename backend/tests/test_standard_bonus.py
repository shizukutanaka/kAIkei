import csv
from datetime import date
from decimal import Decimal

import pytest

from app.services.standard_bonus import BonusEmployee, StandardBonusService


class TestStandardBonusService:
    def test_floor_to_1000(self):
        result = StandardBonusService.compute_standard_bonus(Decimal("345678"))
        assert result.standard_bonus == Decimal("345000")

    def test_health_cap(self):
        result = StandardBonusService.compute_standard_bonus(
            Decimal("100000"),
            fiscal_ytd_standard_bonus=Decimal("5700000"),
        )
        assert result.standard_bonus == Decimal("100000")
        assert result.health_standard_bonus == Decimal("30000")
        assert result.pension_standard_bonus == Decimal("100000")

        capped = StandardBonusService.compute_standard_bonus(
            Decimal("100000"),
            fiscal_ytd_standard_bonus=Decimal("5730000"),
        )
        assert capped.health_standard_bonus == Decimal("0")

    def test_pension_cap(self):
        result = StandardBonusService.compute_standard_bonus(Decimal("2000000"))
        assert result.standard_bonus == Decimal("2000000")
        assert result.pension_standard_bonus == Decimal("1500000")

        capped = StandardBonusService.compute_standard_bonus(
            Decimal("500000"),
            same_month_prior_standard_bonus=Decimal("1500000"),
        )
        assert capped.pension_standard_bonus == Decimal("0")

    def test_small_bonus_under_both_caps(self):
        result = StandardBonusService.compute_standard_bonus(Decimal("123456"))
        assert result.standard_bonus == Decimal("123000")
        assert result.health_standard_bonus == Decimal("123000")
        assert result.pension_standard_bonus == Decimal("123000")

    def test_negative_inputs_raise(self):
        with pytest.raises(ValueError):
            StandardBonusService.compute_standard_bonus(Decimal("-1"))
        with pytest.raises(ValueError):
            StandardBonusService.compute_standard_bonus(
                Decimal("1"),
                fiscal_ytd_standard_bonus=Decimal("-1"),
            )
        with pytest.raises(ValueError):
            StandardBonusService.compute_standard_bonus(
                Decimal("1"),
                same_month_prior_standard_bonus=Decimal("-1"),
            )

    def test_build_csv_empty_raises(self):
        with pytest.raises(ValueError):
            StandardBonusService.build_csv([])

    def test_build_csv_parses_rows(self):
        employees = [
            BonusEmployee(
                insured_number="12345678",
                name="山田 太郎",
                payment_date=date(2025, 6, 10),
                bonus_amount=Decimal("345678"),
                fiscal_ytd_standard_bonus=Decimal("5700000"),
                same_month_prior_standard_bonus=Decimal("0"),
            ),
            BonusEmployee(
                insured_number="87654321",
                name="佐藤 花子",
                payment_date=date(2025, 6, 15),
                bonus_amount=Decimal("500000"),
                fiscal_ytd_standard_bonus=Decimal("5730000"),
                same_month_prior_standard_bonus=Decimal("1500000"),
            ),
        ]
        csv_text = StandardBonusService.build_csv(employees)
        rows = list(csv.reader(csv_text.splitlines()))

        assert len(rows) == 3
        assert rows[0] == [
            "insured_number",
            "name",
            "payment_date",
            "bonus_amount",
            "standard_bonus",
            "health_standard_bonus",
            "pension_standard_bonus",
        ]
        assert rows[1][0] == "12345678"
        assert rows[1][4] == "345000"
        assert rows[1][5] == "30000"
        assert rows[1][6] == "345000"
        assert rows[2][0] == "87654321"
        assert rows[2][4] == "500000"
        assert rows[2][5] == "0"
        assert rows[2][6] == "0"
