from decimal import Decimal

import pytest

from app.services.standard_remuneration import (
    RemunerationMonth,
    StandardRemunerationService,
)


class TestStandardRemunerationService:
    def test_determine_remuneration_monthly_all_qualify(self):
        result = StandardRemunerationService.determine_remuneration_monthly(
            [
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("300000")),
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("305000")),
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("295000")),
            ]
        )
        assert result == Decimal("300000")

    def test_determine_remuneration_monthly_excludes_low_basis_days(self):
        result = StandardRemunerationService.determine_remuneration_monthly(
            [
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("300000")),
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("305000")),
                RemunerationMonth(payment_basis_days=10, remuneration=Decimal("295000")),
            ]
        )
        assert result == Decimal("302500")

    def test_determine_remuneration_monthly_all_excluded(self):
        result = StandardRemunerationService.determine_remuneration_monthly(
            [
                RemunerationMonth(payment_basis_days=10, remuneration=Decimal("300000")),
                RemunerationMonth(payment_basis_days=16, remuneration=Decimal("305000")),
                RemunerationMonth(payment_basis_days=0, remuneration=Decimal("295000")),
            ]
        )
        assert result is None

    def test_determine_remuneration_monthly_empty(self):
        with pytest.raises(ValueError):
            StandardRemunerationService.determine_remuneration_monthly([])

    def test_determine_remuneration_monthly_negative_raises(self):
        with pytest.raises(ValueError):
            StandardRemunerationService.determine_remuneration_monthly(
                [RemunerationMonth(payment_basis_days=-1, remuneration=Decimal("300000"))]
            )
        with pytest.raises(ValueError):
            StandardRemunerationService.determine_remuneration_monthly(
                [RemunerationMonth(payment_basis_days=20, remuneration=Decimal("-1"))]
            )

    def test_lookup_300000_maps_to_matching_health_and_pension_grades(self):
        health = StandardRemunerationService.lookup_health_grade(Decimal("300000"))
        pension = StandardRemunerationService.lookup_pension_grade(Decimal("300000"))

        assert health.standard_monthly_remuneration == Decimal("300000")
        assert pension.standard_monthly_remuneration == Decimal("300000")
        assert health.grade == 22
        assert pension.grade == 19

    def test_lookup_high_remuneration_caps_pension_and_uses_health_table(self):
        health = StandardRemunerationService.lookup_health_grade(Decimal("1000000"))
        pension = StandardRemunerationService.lookup_pension_grade(Decimal("1000000"))

        assert pension.standard_monthly_remuneration == Decimal("650000")
        assert pension.grade == 32
        assert health.standard_monthly_remuneration == Decimal("980000")
        assert health.grade == 43

    def test_lookup_minimum(self):
        health = StandardRemunerationService.lookup_health_grade(Decimal("50000"))
        pension = StandardRemunerationService.lookup_pension_grade(Decimal("50000"))

        assert health.standard_monthly_remuneration == Decimal("58000")
        assert health.grade == 1
        assert pension.standard_monthly_remuneration == Decimal("88000")
        assert pension.grade == 1

    def test_lookup_negative_raises(self):
        with pytest.raises(ValueError):
            StandardRemunerationService.lookup_health_grade(Decimal("-1"))
        with pytest.raises(ValueError):
            StandardRemunerationService.lookup_pension_grade(Decimal("-1"))
