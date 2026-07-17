import csv
from datetime import date
from decimal import Decimal

import pytest

from app.services.qualification_acquisition import AcquisitionEmployee, QualificationAcquisitionService


class TestQualificationAcquisitionService:
    def test_compute_employee_defaults(self):
        result = QualificationAcquisitionService.compute_employee(
            AcquisitionEmployee(
                insured_number="12345678",
                name="山田 太郎",
                birth_date=date(1990, 1, 1),
                qualification_date=date(2025, 4, 1),
                estimated_monthly_remuneration=Decimal("300000"),
            )
        )

        assert result.health_grade.grade == 22
        assert result.health_grade.standard_monthly_remuneration == Decimal("300000")
        assert result.pension_grade.grade == 19
        assert result.pension_grade.standard_monthly_remuneration == Decimal("300000")

    def test_compute_employee_pension_caps(self):
        result = QualificationAcquisitionService.compute_employee(
            AcquisitionEmployee(
                insured_number="12345678",
                name="山田 太郎",
                birth_date=date(1990, 1, 1),
                qualification_date=date(2025, 4, 1),
                estimated_monthly_remuneration=Decimal("700000"),
            )
        )

        assert result.pension_grade.grade == 32
        assert result.pension_grade.standard_monthly_remuneration == Decimal("650000")
        assert result.health_grade.standard_monthly_remuneration == Decimal("710000")

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            QualificationAcquisitionService.compute_employee(
                AcquisitionEmployee(
                    insured_number="12345678",
                    name="山田 太郎",
                    birth_date=date(1990, 1, 1),
                    qualification_date=date(2025, 4, 1),
                    estimated_monthly_remuneration=Decimal("-1"),
                )
            )

    def test_build_csv_empty_raises(self):
        with pytest.raises(ValueError):
            QualificationAcquisitionService.build_csv([])

    def test_build_csv_parses_rows(self):
        employees = [
            AcquisitionEmployee(
                insured_number="12345678",
                name="山田 太郎",
                birth_date=date(1990, 1, 1),
                qualification_date=date(2025, 4, 1),
                estimated_monthly_remuneration=Decimal("300000"),
            ),
            AcquisitionEmployee(
                insured_number="87654321",
                name="佐藤 花子",
                birth_date=date(1992, 2, 2),
                qualification_date=date(2025, 5, 1),
                estimated_monthly_remuneration=Decimal("700000"),
            ),
        ]
        csv_text = QualificationAcquisitionService.build_csv(employees)
        rows = list(csv.reader(csv_text.splitlines()))

        assert len(rows) == 3
        assert rows[0] == [
            "insured_number",
            "name",
            "birth_date",
            "qualification_date",
            "estimated_monthly_remuneration",
            "health_grade",
            "health_standard",
            "pension_grade",
            "pension_standard",
        ]
        assert rows[1][6] == "300000"
        assert rows[2][8] == "650000"
