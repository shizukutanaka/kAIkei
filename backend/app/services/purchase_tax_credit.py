"""一般課税の仕入税額控除の計算(消費税法30条)。

課税売上割合と、課税仕入等の税額から控除対象仕入税額を計算する。
課税売上割合が95%未満、または課税売上高が5億円超の場合は、次のいずれかの
方法で控除税額を按分する。

課税売上割合:
  課税売上割合 = (課税売上高 + 免税売上高) / (課税売上高 + 免税売上高 + 非課税売上高)
  ※本サービスでは taxable_sales に免税売上(輸出)を含めて渡す。

個別対応方式:
  控除税額 = 課税売上にのみ要する税額
           + 共通して要する税額 × 課税売上割合

一括比例配分方式:
  控除税額 = 課税仕入等の税額の合計 × 課税売上割合
  ※一度選択すると2年間継続適用が必要(判断は利用側)。

全額控除(95%ルール):
  課税売上割合が95%以上 かつ その課税期間の課税売上高が5億円以下の場合は、
  課税仕入等の税額の全額を控除できる。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

FULL_DEDUCTION_RATIO_THRESHOLD = Decimal("0.95")
FULL_DEDUCTION_SALES_LIMIT = Decimal("500000000")  # 5億円


@dataclass(frozen=True)
class PurchaseTaxCreditResult:
    taxable_ratio: Decimal
    full_deduction: bool
    input_tax_total: Decimal
    individual_method_credit: Decimal
    proportional_method_credit: Decimal


class PurchaseTaxCreditService:
    """控除対象仕入税額を算定する純粋サービス。"""

    @staticmethod
    def compute(
        *,
        taxable_sales: Decimal,
        non_taxable_sales: Decimal,
        input_tax_taxable_only: Decimal,
        input_tax_common: Decimal,
        input_tax_nontaxable_only: Decimal = Decimal("0"),
    ) -> PurchaseTaxCreditResult:
        if taxable_sales < 0:
            raise ValueError("taxable_sales must not be negative")
        if non_taxable_sales < 0:
            raise ValueError("non_taxable_sales must not be negative")
        for value in (
            input_tax_taxable_only,
            input_tax_common,
            input_tax_nontaxable_only,
        ):
            if value < 0:
                raise ValueError("input tax amounts must not be negative")

        denominator = taxable_sales + non_taxable_sales
        if denominator <= 0:
            raise ValueError("total sales must be positive")

        taxable_ratio = taxable_sales / denominator
        input_tax_total = (
            input_tax_taxable_only + input_tax_common + input_tax_nontaxable_only
        )

        full_deduction = (
            taxable_ratio >= FULL_DEDUCTION_RATIO_THRESHOLD
            and taxable_sales <= FULL_DEDUCTION_SALES_LIMIT
        )

        if full_deduction:
            individual = input_tax_total
            proportional = input_tax_total
        else:
            common_credit = (input_tax_common * taxable_ratio).quantize(
                Decimal("1"), rounding=ROUND_DOWN
            )
            individual = input_tax_taxable_only + common_credit
            proportional = (input_tax_total * taxable_ratio).quantize(
                Decimal("1"), rounding=ROUND_DOWN
            )

        return PurchaseTaxCreditResult(
            taxable_ratio=taxable_ratio,
            full_deduction=full_deduction,
            input_tax_total=input_tax_total,
            individual_method_credit=individual,
            proportional_method_credit=proportional,
        )
