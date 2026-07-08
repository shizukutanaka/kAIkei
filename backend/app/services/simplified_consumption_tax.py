from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# 消費税の簡易課税制度におけるみなし仕入率
SIMPLIFIED_CONSUMPTION_TAX_RATES: dict[int, Decimal] = {
    1: Decimal("0.90"),  # 第1種卸売業
    2: Decimal("0.80"),  # 第2種小売業
    3: Decimal("0.70"),  # 第3種製造業等
    4: Decimal("0.60"),  # 第4種その他
    5: Decimal("0.50"),  # 第5種サービス業等
    6: Decimal("0.40"),  # 第6種不動産業
}


@dataclass(frozen=True)
class SimplifiedConsumptionTaxResult:
    business_category: int
    deemed_purchase_rate: Decimal
    deductible_tax: Decimal
    net_tax: Decimal


class SimplifiedConsumptionTaxService:
    @staticmethod
    def compute(sales_tax: Decimal, business_category: int) -> SimplifiedConsumptionTaxResult:
        if sales_tax < 0:
            raise ValueError("sales_tax must be non-negative")
        try:
            rate = SIMPLIFIED_CONSUMPTION_TAX_RATES[business_category]
        except KeyError as exc:
            raise ValueError(f"Unsupported business_category: {business_category}") from exc

        deductible_tax = (sales_tax * rate).quantize(Decimal("1"), rounding=ROUND_DOWN)
        net_tax = sales_tax - deductible_tax
        return SimplifiedConsumptionTaxResult(
            business_category=business_category,
            deemed_purchase_rate=rate,
            deductible_tax=deductible_tax,
            net_tax=net_tax,
        )
