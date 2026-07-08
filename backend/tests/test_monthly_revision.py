import csv
from decimal import Decimal

import pytest

from app.services.monthly_revision import MonthlyRevisionService, RevisionEmployee
from app.services.standard_remuneration import RemunerationMonth


class TestMonthlyRevisionService:
    def test_revision_required_true(self):
        result = MonthlyRevisionService.judge(
            previous_health_standard=Decimal("300000"),
            previous_pension_standard=Decimal("300000"),
            months=[
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
            ],
            fixed_wage_changed=True,
        )

        assert result.average == Decimal("380000")
        assert result.prev_health.grade == 22
        assert result.new_health is not None
        assert result.new_health.grade == 26
        assert result.health_grade_diff == 4
        assert result.revision_required is True
        assert result.reason == "eligible"

    def test_grade_diff_below_2(self):
        result = MonthlyRevisionService.judge(
            previous_health_standard=Decimal("300000"),
            previous_pension_standard=Decimal("300000"),
            months=[
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("310000")),
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("310000")),
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("310000")),
            ],
            fixed_wage_changed=True,
        )

        assert result.average == Decimal("310000")
        assert result.new_health is not None
        assert result.new_health.grade == 23
        assert result.health_grade_diff == 1
        assert result.revision_required is False
        assert result.reason == "grade_diff_below_2"

    def test_insufficient_days(self):
        result = MonthlyRevisionService.judge(
            previous_health_standard=Decimal("300000"),
            previous_pension_standard=Decimal("300000"),
            months=[
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
                RemunerationMonth(payment_basis_days=15, remuneration=Decimal("380000")),
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
            ],
            fixed_wage_changed=True,
        )

        assert result.days_ok is False
        assert result.average is None
        assert result.revision_required is False
        assert result.reason == "insufficient_days"

    def test_fixed_wage_not_changed(self):
        result = MonthlyRevisionService.judge(
            previous_health_standard=Decimal("300000"),
            previous_pension_standard=Decimal("300000"),
            months=[
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
                RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
            ],
            fixed_wage_changed=False,
        )

        assert result.revision_required is False
        assert result.reason == "fixed_wage_not_changed"

    def test_invalid_month_count_and_negative_previous_raise(self):
        with pytest.raises(ValueError):
            MonthlyRevisionService.judge(
                previous_health_standard=Decimal("300000"),
                previous_pension_standard=Decimal("300000"),
                months=[RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000"))],
                fixed_wage_changed=True,
            )
        with pytest.raises(ValueError):
            MonthlyRevisionService.judge(
                previous_health_standard=Decimal("-1"),
                previous_pension_standard=Decimal("300000"),
                months=[
                    RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
                    RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
                    RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
                ],
                fixed_wage_changed=True,
            )

    def test_build_csv(self):
        employees = [
            RevisionEmployee(
                insured_number="12345678",
                name="山田 太郎",
                previous_health_standard=Decimal("300000"),
                previous_pension_standard=Decimal("300000"),
                fixed_wage_changed=True,
                months=[
                    RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
                    RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
                    RemunerationMonth(payment_basis_days=20, remuneration=Decimal("380000")),
                ],
            ),
            RevisionEmployee(
                insured_number="87654321",
                name="佐藤 花子",
                previous_health_standard=Decimal("300000"),
                previous_pension_standard=Decimal("300000"),
                fixed_wage_changed=False,
                months=[
                    RemunerationMonth(payment_basis_days=20, remuneration=Decimal("310000")),
                    RemunerationMonth(payment_basis_days=20, remuneration=Decimal("310000")),
                    RemunerationMonth(payment_basis_days=20, remuneration=Decimal("310000")),
                ],
            ),
        ]

        csv_text = MonthlyRevisionService.build_csv(employees)
        rows = list(csv.reader(csv_text.splitlines()))

        assert len(rows) == 3
        assert rows[0] == [
            "insured_number",
            "name",
            "fixed_wage_changed",
            "days_ok",
            "average",
            "prev_health_grade",
            "new_health_grade",
            "health_grade_diff",
            "prev_pension_grade",
            "new_pension_grade",
            "revision_required",
            "reason",
        ]
        assert rows[1][0] == "12345678"
        assert rows[1][10] == "True"
        assert rows[1][11] == "eligible"
        assert rows[2][0] == "87654321"
        assert rows[2][10] == "False"
        assert rows[2][11] == "fixed_wage_not_changed"

    def test_build_csv_empty_raises(self):
        with pytest.raises(ValueError):
            MonthlyRevisionService.build_csv([])
