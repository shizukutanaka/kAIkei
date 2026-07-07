import csv
from decimal import Decimal

import pytest

from app.services.labor_insurance import BUSINESS_TYPE_GENERAL
from app.services.labor_insurance_annual import LaborInsuranceAnnualUpdateService


class TestLaborInsuranceAnnualUpdateService:
    def test_compute_general_business_case(self):
        result = LaborInsuranceAnnualUpdateService.compute(
            prior_wage_total=Decimal("12345678"),
            estimated_wage_total=Decimal("12345678"),
            business_type=BUSINESS_TYPE_GENERAL,
            declared_prior_estimate=Decimal("200000"),
        )

        assert result.confirmed_base == Decimal("12345000")
        assert result.estimated_base == Decimal("12345000")
        assert result.employment_rate == Decimal("0.0155")
        assert result.workers_comp_rate == Decimal("0.003")
        assert result.determined_premium == Decimal("228382")
        assert result.estimated_premium == Decimal("228382")
        assert result.general_contribution == Decimal("246")
        assert result.declared_prior_estimate == Decimal("200000")
        assert result.settlement == Decimal("28382")
        assert result.settlement_kind == "shortfall"
        assert result.total_payment == Decimal("257010")

    def test_settlement_kinds(self):
        excess = LaborInsuranceAnnualUpdateService.compute(
            prior_wage_total=Decimal("12345678"),
            estimated_wage_total=Decimal("12345678"),
            business_type=BUSINESS_TYPE_GENERAL,
            declared_prior_estimate=Decimal("250000"),
        )
        even = LaborInsuranceAnnualUpdateService.compute(
            prior_wage_total=Decimal("12345678"),
            estimated_wage_total=Decimal("12345678"),
            business_type=BUSINESS_TYPE_GENERAL,
            declared_prior_estimate=Decimal("228382"),
        )
        shortfall = LaborInsuranceAnnualUpdateService.compute(
            prior_wage_total=Decimal("12345678"),
            estimated_wage_total=Decimal("12345678"),
            business_type=BUSINESS_TYPE_GENERAL,
            declared_prior_estimate=Decimal("200000"),
        )

        assert excess.settlement == Decimal("-21618")
        assert excess.settlement_kind == "excess"
        assert even.settlement == Decimal("0")
        assert even.settlement_kind == "even"
        assert shortfall.settlement == Decimal("28382")
        assert shortfall.settlement_kind == "shortfall"

    def test_floor_to_1000(self):
        assert LaborInsuranceAnnualUpdateService.floor_to_1000(Decimal("999")) == Decimal("0")
        assert LaborInsuranceAnnualUpdateService.floor_to_1000(Decimal("1000")) == Decimal("1000")
        assert LaborInsuranceAnnualUpdateService.floor_to_1000(Decimal("1999")) == Decimal("1000")

    def test_unsupported_business_type_raises(self):
        with pytest.raises(ValueError):
            LaborInsuranceAnnualUpdateService.compute(
                prior_wage_total=Decimal("1000"),
                estimated_wage_total=Decimal("1000"),
                business_type="unsupported",
                declared_prior_estimate=Decimal("0"),
            )

    def test_negative_inputs_raise(self):
        with pytest.raises(ValueError):
            LaborInsuranceAnnualUpdateService.compute(
                prior_wage_total=Decimal("-1"),
                estimated_wage_total=Decimal("1000"),
                business_type=BUSINESS_TYPE_GENERAL,
                declared_prior_estimate=Decimal("0"),
            )
        with pytest.raises(ValueError):
            LaborInsuranceAnnualUpdateService.compute(
                prior_wage_total=Decimal("1000"),
                estimated_wage_total=Decimal("-1"),
                business_type=BUSINESS_TYPE_GENERAL,
                declared_prior_estimate=Decimal("0"),
            )
        with pytest.raises(ValueError):
            LaborInsuranceAnnualUpdateService.compute(
                prior_wage_total=Decimal("1000"),
                estimated_wage_total=Decimal("1000"),
                business_type=BUSINESS_TYPE_GENERAL,
                declared_prior_estimate=Decimal("-1"),
            )

    def test_build_csv(self):
        result = LaborInsuranceAnnualUpdateService.compute(
            prior_wage_total=Decimal("12345678"),
            estimated_wage_total=Decimal("12345678"),
            business_type=BUSINESS_TYPE_GENERAL,
            declared_prior_estimate=Decimal("200000"),
        )
        csv_text = LaborInsuranceAnnualUpdateService.build_csv(result)
        rows = list(csv.reader(csv_text.splitlines()))

        assert len(rows) == 2
        assert rows[0] == [
            "business_type",
            "confirmed_base",
            "estimated_base",
            "employment_rate",
            "workers_comp_rate",
            "determined_premium",
            "estimated_premium",
            "general_contribution",
            "declared_prior_estimate",
            "settlement",
            "settlement_kind",
            "total_payment",
        ]
        assert rows[1][0] == BUSINESS_TYPE_GENERAL
        assert rows[1][1] == "12345000"
        assert rows[1][2] == "12345000"
        assert rows[1][3] == "0.0155"
        assert rows[1][4] == "0.003"
        assert rows[1][5] == "228382"
        assert rows[1][6] == "228382"
        assert rows[1][7] == "246"
        assert rows[1][8] == "200000"
        assert rows[1][9] == "28382"
        assert rows[1][10] == "shortfall"
        assert rows[1][11] == "257010"
