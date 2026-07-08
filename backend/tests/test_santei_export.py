import csv
from datetime import date
from decimal import Decimal

import pytest

from app.services.santei_export import SanteiEmployee, SanteiKisoService, SanteiMonth


class TestSanteiKisoService:
    def test_compute_employee_all_qualify(self):
        emp = SanteiEmployee(
            insured_number="12345678",
            name="山田 太郎",
            birth_date=date(1990, 1, 2),
            previous_health_standard=Decimal("280000"),
            previous_pension_standard=Decimal("280000"),
            applicable_year=2025,
            applicable_month=6,
            months=[
                SanteiMonth(payment_basis_days=20, currency_remuneration=Decimal("290000"), in_kind_remuneration=Decimal("10000")),
                SanteiMonth(payment_basis_days=20, currency_remuneration=Decimal("290000"), in_kind_remuneration=Decimal("10000")),
                SanteiMonth(payment_basis_days=20, currency_remuneration=Decimal("290000"), in_kind_remuneration=Decimal("10000")),
            ],
        )

        result = SanteiKisoService.compute_employee(emp)

        assert result.total == Decimal("900000")
        assert result.average == Decimal("300000")
        assert result.requires_manual is False
        assert result.health_grade is not None
        assert result.health_grade.grade == 22
        assert result.health_grade.standard_monthly_remuneration == Decimal("300000")
        assert result.pension_grade is not None
        assert result.pension_grade.grade == 19
        assert result.pension_grade.standard_monthly_remuneration == Decimal("300000")

    def test_compute_employee_excludes_low_basis_days(self):
        emp = SanteiEmployee(
            insured_number="12345678",
            name="山田 太郎",
            birth_date=date(1990, 1, 2),
            previous_health_standard=Decimal("280000"),
            previous_pension_standard=Decimal("280000"),
            applicable_year=2025,
            applicable_month=6,
            months=[
                SanteiMonth(payment_basis_days=20, currency_remuneration=Decimal("300000"), in_kind_remuneration=Decimal("0")),
                SanteiMonth(payment_basis_days=20, currency_remuneration=Decimal("360000"), in_kind_remuneration=Decimal("0")),
                SanteiMonth(payment_basis_days=16, currency_remuneration=Decimal("100000"), in_kind_remuneration=Decimal("0")),
            ],
        )

        result = SanteiKisoService.compute_employee(emp)

        assert result.total == Decimal("660000")
        assert result.average == Decimal("330000")
        assert result.health_grade is not None
        assert result.health_grade.standard_monthly_remuneration == Decimal("340000")
        assert result.pension_grade is not None
        assert result.pension_grade.standard_monthly_remuneration == Decimal("340000")

    def test_compute_employee_requires_manual_when_no_month_qualifies(self):
        emp = SanteiEmployee(
            insured_number="12345678",
            name="山田 太郎",
            birth_date=date(1990, 1, 2),
            previous_health_standard=Decimal("280000"),
            previous_pension_standard=Decimal("280000"),
            applicable_year=2025,
            applicable_month=6,
            months=[
                SanteiMonth(payment_basis_days=16, currency_remuneration=Decimal("300000"), in_kind_remuneration=Decimal("0")),
                SanteiMonth(payment_basis_days=10, currency_remuneration=Decimal("360000"), in_kind_remuneration=Decimal("0")),
                SanteiMonth(payment_basis_days=0, currency_remuneration=Decimal("100000"), in_kind_remuneration=Decimal("0")),
            ],
        )

        result = SanteiKisoService.compute_employee(emp)

        assert result.average is None
        assert result.requires_manual is True
        assert result.health_grade is None
        assert result.pension_grade is None
        assert result.total == Decimal("0")

    def test_build_csv_writes_header_and_rows(self):
        valid_employee = SanteiEmployee(
            insured_number="12345678",
            name="山田 太郎",
            birth_date=date(1990, 1, 2),
            previous_health_standard=Decimal("280000"),
            previous_pension_standard=Decimal("280000"),
            applicable_year=2025,
            applicable_month=6,
            months=[
                SanteiMonth(payment_basis_days=20, currency_remuneration=Decimal("290000"), in_kind_remuneration=Decimal("10000")),
                SanteiMonth(payment_basis_days=20, currency_remuneration=Decimal("290000"), in_kind_remuneration=Decimal("10000")),
                SanteiMonth(payment_basis_days=20, currency_remuneration=Decimal("290000"), in_kind_remuneration=Decimal("10000")),
            ],
        )
        manual_employee = SanteiEmployee(
            insured_number="87654321",
            name="佐藤 花子",
            birth_date=date(1988, 7, 8),
            previous_health_standard=Decimal("260000"),
            previous_pension_standard=Decimal("260000"),
            applicable_year=2025,
            applicable_month=6,
            months=[
                SanteiMonth(payment_basis_days=16, currency_remuneration=Decimal("300000"), in_kind_remuneration=Decimal("0")),
                SanteiMonth(payment_basis_days=10, currency_remuneration=Decimal("300000"), in_kind_remuneration=Decimal("0")),
                SanteiMonth(payment_basis_days=0, currency_remuneration=Decimal("300000"), in_kind_remuneration=Decimal("0")),
            ],
        )

        csv_text = SanteiKisoService.build_csv([valid_employee, manual_employee])
        rows = list(csv.reader(csv_text.splitlines()))

        assert len(rows) == 3
        assert rows[0][0] == "insured_number"
        assert rows[1][0] == "12345678"
        assert rows[1][19] == "300000"
        assert rows[1][21] == "300000"
        assert rows[1][23] == "300000"
        assert rows[1][24] == "False"
        assert rows[2][0] == "87654321"
        assert rows[2][19] == ""
        assert rows[2][21] == ""
        assert rows[2][23] == ""
        assert rows[2][24] == "True"

    def test_build_csv_empty_employees_raises(self):
        with pytest.raises(ValueError):
            SanteiKisoService.build_csv([])
