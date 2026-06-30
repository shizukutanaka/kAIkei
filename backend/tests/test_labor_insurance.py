from decimal import Decimal

from app.services.labor_insurance import (
    BUSINESS_TYPE_AGRICULTURE_FORESTRY_FISHERY_SAKE,
    BUSINESS_TYPE_CONSTRUCTION,
    BUSINESS_TYPE_GENERAL,
    DEFAULT_WORKERS_COMPENSATION_RATE,
    LaborInsuranceService,
)


class TestLaborInsuranceService:
    def test_ut_pay_003_general_invariant(self):
        result = LaborInsuranceService.calculate_employee_premium(
            gross_monthly_pay=Decimal("300000"),
            business_type=BUSINESS_TYPE_GENERAL,
            age=40,
            workers_comp_rate=DEFAULT_WORKERS_COMPENSATION_RATE,
        )

        assert result.employment_insurance_employee == Decimal("1800")
        assert result.employment_insurance_employer == Decimal("2850")
        assert result.workers_comp_employer == Decimal("900")
        assert result.total_employee == Decimal("1800")
        assert result.total_employer == Decimal("3750")
        assert result.total_premium == Decimal("5550")

    def test_construction_and_agriculture_rates(self):
        construction = LaborInsuranceService.calculate_employee_premium(
            gross_monthly_pay=Decimal("200000"),
            business_type=BUSINESS_TYPE_CONSTRUCTION,
            age=30,
            workers_comp_rate=Decimal("0.003"),
        )
        agriculture = LaborInsuranceService.calculate_employee_premium(
            gross_monthly_pay=Decimal("200000"),
            business_type=BUSINESS_TYPE_AGRICULTURE_FORESTRY_FISHERY_SAKE,
            age=30,
            workers_comp_rate=Decimal("0.003"),
        )

        assert construction.employment_insurance_employee == Decimal("1400")
        assert construction.employment_insurance_employer == Decimal("2100")
        assert agriculture.employment_insurance_employee == Decimal("1400")
        assert agriculture.employment_insurance_employer == Decimal("2100")

    def test_sixty_five_or_over_exempts_employment_insurance_but_not_workers_comp(self):
        result = LaborInsuranceService.calculate_employee_premium(
            gross_monthly_pay=Decimal("250000"),
            business_type=BUSINESS_TYPE_GENERAL,
            age=65,
            workers_comp_rate=Decimal("0.003"),
        )

        assert result.employment_insurance_employee == Decimal("0")
        assert result.employment_insurance_employer == Decimal("0")
        assert result.workers_comp_employer == Decimal("750")
        assert result.total_employee == Decimal("0")
        assert result.total_employer == Decimal("750")
        assert result.total_premium == Decimal("750")

    def test_workers_comp_is_employer_only(self):
        result = LaborInsuranceService.calculate_employee_premium(
            gross_monthly_pay=Decimal("100000"),
            business_type=BUSINESS_TYPE_GENERAL,
            age=30,
            workers_comp_rate=Decimal("0.01"),
        )

        assert result.employment_insurance_employee == Decimal("600")
        assert result.employment_insurance_employer == Decimal("950")
        assert result.workers_comp_employer == Decimal("1000")
        assert result.total_employee == Decimal("600")
        assert result.total_employer == Decimal("1950")
        assert result.total_premium == Decimal("2550")

    def test_company_aggregation_sums_correctly(self):
        items = [
            LaborInsuranceService.calculate_employee_premium(
                gross_monthly_pay=Decimal("300000"),
                business_type=BUSINESS_TYPE_GENERAL,
                age=40,
                workers_comp_rate=Decimal("0.003"),
            ),
            LaborInsuranceService.calculate_employee_premium(
                gross_monthly_pay=Decimal("250000"),
                business_type=BUSINESS_TYPE_GENERAL,
                age=65,
                workers_comp_rate=Decimal("0.003"),
            ),
        ]

        summary = LaborInsuranceService.summarize_company_premiums(items)

        assert summary.employee_count == 2
        assert summary.total_employee_premium == Decimal("1800")
        assert summary.total_employer_premium == Decimal("4500")
        assert summary.total_premium == Decimal("6300")
        assert summary.items == items
