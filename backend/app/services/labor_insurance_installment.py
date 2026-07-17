from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# 徴収法の概算保険料の延納基準額。労災・雇用の両保険成立時。
INSTALLMENT_THRESHOLD_BOTH_INSURANCES = Decimal("400000")
# 徴収法の概算保険料の延納基準額。労災・雇用のいずれか一方のみ成立時。
INSTALLMENT_THRESHOLD_SINGLE_INSURANCE = Decimal("200000")


@dataclass(frozen=True)
class InstallmentResult:
    estimated_premium: Decimal
    threshold: Decimal
    both_insurances: bool
    entrusted: bool
    eligible: bool
    installment_count: int
    installments: list[Decimal]
    note: str


class LaborInsuranceInstallmentService:
    @classmethod
    def compute(
        cls,
        estimated_premium: Decimal,
        both_insurances: bool = True,
        entrusted: bool = False,
    ) -> InstallmentResult:
        if estimated_premium < 0:
            raise ValueError("estimated_premium must be non-negative")

        threshold = (
            INSTALLMENT_THRESHOLD_BOTH_INSURANCES
            if both_insurances
            else INSTALLMENT_THRESHOLD_SINGLE_INSURANCE
        )
        eligible = entrusted or estimated_premium >= threshold

        if not eligible:
            installments = [estimated_premium]
            installment_count = 1
        else:
            base = (estimated_premium / Decimal("3")).quantize(Decimal("1"), rounding=ROUND_DOWN)
            remainder = estimated_premium - (base * Decimal("3"))
            installments = [base + remainder, base, base]
            installment_count = 3
            assert sum(installments, Decimal("0")) == estimated_premium

        return InstallmentResult(
            estimated_premium=estimated_premium,
            threshold=threshold,
            both_insurances=both_insurances,
            entrusted=entrusted,
            eligible=eligible,
            installment_count=installment_count,
            installments=installments,
            note="一般拠出金・確定保険料の不足額は分割対象外（第1期に納付）",
        )
