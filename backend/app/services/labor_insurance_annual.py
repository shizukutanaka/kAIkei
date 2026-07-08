"""労働保険 年度更新の電子申請連携用データ生成。

This CSV is a structured 連携用データ following 年度更新申告書 記載事項.
It is NOT byte-verified against a specific e-Gov CSV仕様書 version and should
be mapped to the exact e-Gov 社会保険手続CSV layout at integration time.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from io import StringIO

from app.services.labor_insurance import DEFAULT_WORKERS_COMPENSATION_RATE, LaborInsuranceService

# 一般拠出金（石綿健康被害救済法）: 賃金総額1000円につき0.02円 = 0.00002
GENERAL_CONTRIBUTION_RATE = Decimal("0.00002")


@dataclass(frozen=True)
class AnnualUpdateResult:
    business_type: str
    confirmed_base: Decimal
    estimated_base: Decimal
    employment_rate: Decimal
    workers_comp_rate: Decimal
    determined_premium: Decimal
    estimated_premium: Decimal
    general_contribution: Decimal
    declared_prior_estimate: Decimal
    settlement: Decimal
    settlement_kind: str
    total_payment: Decimal


class LaborInsuranceAnnualUpdateService:
    @staticmethod
    def floor_to_1000(amount: Decimal) -> Decimal:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        thousands = (amount / Decimal("1000")).quantize(Decimal("1"), rounding=ROUND_DOWN)
        return thousands * Decimal("1000")

    @staticmethod
    def _whole_yen(amount: Decimal) -> Decimal:
        return amount.quantize(Decimal("1"), rounding=ROUND_DOWN)

    @classmethod
    def compute(
        cls,
        prior_wage_total: Decimal,
        estimated_wage_total: Decimal,
        business_type: str,
        declared_prior_estimate: Decimal,
        workers_comp_rate: Decimal = DEFAULT_WORKERS_COMPENSATION_RATE,
    ) -> AnnualUpdateResult:
        if prior_wage_total < 0 or estimated_wage_total < 0 or declared_prior_estimate < 0:
            raise ValueError("wage totals and declared_prior_estimate must be non-negative")

        total_rate = LaborInsuranceService.combined_rate(business_type, workers_comp_rate)
        employment_rate = total_rate - workers_comp_rate
        confirmed_base = cls.floor_to_1000(prior_wage_total)
        estimated_base = cls.floor_to_1000(estimated_wage_total)
        determined_premium = cls._whole_yen(confirmed_base * total_rate)
        estimated_premium = cls._whole_yen(estimated_base * total_rate)
        general_contribution = cls._whole_yen(confirmed_base * GENERAL_CONTRIBUTION_RATE)
        settlement = determined_premium - declared_prior_estimate
        if settlement > 0:
            settlement_kind = "shortfall"
        elif settlement < 0:
            settlement_kind = "excess"
        else:
            settlement_kind = "even"
        total_payment = estimated_premium + settlement + general_contribution
        return AnnualUpdateResult(
            business_type=business_type,
            confirmed_base=confirmed_base,
            estimated_base=estimated_base,
            employment_rate=employment_rate,
            workers_comp_rate=workers_comp_rate,
            determined_premium=determined_premium,
            estimated_premium=estimated_premium,
            general_contribution=general_contribution,
            declared_prior_estimate=declared_prior_estimate,
            settlement=settlement,
            settlement_kind=settlement_kind,
            total_payment=total_payment,
        )

    @staticmethod
    def build_csv(result: AnnualUpdateResult) -> str:
        buffer = StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow([
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
        ])
        writer.writerow([
            result.business_type,
            result.confirmed_base,
            result.estimated_base,
            result.employment_rate,
            result.workers_comp_rate,
            result.determined_premium,
            result.estimated_premium,
            result.general_contribution,
            result.declared_prior_estimate,
            result.settlement,
            result.settlement_kind,
            result.total_payment,
        ])
        return buffer.getvalue()
