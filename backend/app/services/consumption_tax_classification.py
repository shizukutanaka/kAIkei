"""仕訳の税区分から、消費税申告の課税区分別金額を集計する。

申告書の課税売上・課税仕入は、本来は仕訳明細に紐づく税区分（`tax_rules`）から
集計する。しかし実装は売上・費用を一律 80%/20% で按分しており、コード上も
`"Simplified: assume 80% of revenue is taxable"` と placeholder であることが
書かれていた。申告書はそのまま提出されうるので、実データから集計する。

`TaxRule.tax_type` の値ごとに、申告書のどの欄へ入るかを決める:

    taxable       課税取引（税率10%/8%）→ 課税売上・課税仕入
    export        輸出免税（消費税法7条）→ 免税売上。売上は0%だが仕入税額控除は可能
    non_taxable   非課税（6条・別表第二: 土地、利子、住宅家賃等）→ 課税対象外
    exempt        不課税/対象外（給与、寄付金、配当等）→ 課税対象外

税区分が付いていない明細（`tax_rule_id` が NULL）は判定できない。黙って
課税扱いにも非課税扱いにもせず、件数と金額を返して呼び出し側が利用者に
示せるようにする。**分からないものを分かったことにしない。**
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

# TaxRule.tax_type が取りうる値と、申告書上の扱い。
TAXABLE = "taxable"
EXPORT = "export"
NON_TAXABLE = "non_taxable"
EXEMPT = "exempt"

#: 課税売上割合の分母に入る（課税＋免税＋非課税）。不課税は資産の譲渡等に
#: 当たらないため分母にも入らない（消費税法30条6項）。
_IN_SALES_TOTAL = frozenset({TAXABLE, EXPORT, NON_TAXABLE})


@dataclass(frozen=True)
class TaxClassifiedAmounts:
    """税区分別の集計結果。金額はいずれも税抜の本体価額。"""

    taxable: Decimal = Decimal("0")
    export: Decimal = Decimal("0")
    non_taxable: Decimal = Decimal("0")
    exempt: Decimal = Decimal("0")
    #: 税区分が未設定だった明細の合計額と件数。
    unclassified: Decimal = Decimal("0")
    unclassified_count: int = 0
    #: 税率ごとの課税取引額（軽減税率の区分に使う）。key は税率（0.10 等）。
    taxable_by_rate: dict[Decimal, Decimal] = field(default_factory=dict)

    @property
    def total(self) -> Decimal:
        """申告書上の合計（未分類を含む）。"""
        return self.taxable + self.export + self.non_taxable + self.exempt + self.unclassified

    @property
    def sales_total_for_ratio(self) -> Decimal:
        """課税売上割合の分母（課税＋免税＋非課税）。"""
        return self.taxable + self.export + self.non_taxable

    @property
    def has_unclassified(self) -> bool:
        return self.unclassified_count > 0


def classify(rows: list[tuple[str | None, Decimal | None, Decimal]]) -> TaxClassifiedAmounts:
    """`(tax_type, tax_rate, amount)` の並びを税区分別に集計する。

    `tax_type` が None の行は未分類として別に数える。未知の `tax_type` も
    未分類に含める（新しい区分が増えたときに黙って課税へ倒さないため）。
    """
    buckets: dict[str, Decimal] = {TAXABLE: Decimal("0"), EXPORT: Decimal("0"),
                                   NON_TAXABLE: Decimal("0"), EXEMPT: Decimal("0")}
    unclassified = Decimal("0")
    unclassified_count = 0
    by_rate: dict[Decimal, Decimal] = {}

    for tax_type, tax_rate, amount in rows:
        if amount is None:
            continue
        if tax_type in buckets:
            buckets[tax_type] += amount
            if tax_type == TAXABLE:
                rate = tax_rate if tax_rate is not None else Decimal("0")
                by_rate[rate] = by_rate.get(rate, Decimal("0")) + amount
        else:
            unclassified += amount
            unclassified_count += 1

    return TaxClassifiedAmounts(
        taxable=buckets[TAXABLE],
        export=buckets[EXPORT],
        non_taxable=buckets[NON_TAXABLE],
        exempt=buckets[EXEMPT],
        unclassified=unclassified,
        unclassified_count=unclassified_count,
        taxable_by_rate=by_rate,
    )


def output_tax(amounts: TaxClassifiedAmounts) -> Decimal:
    """課税売上に対する消費税額。税率ごとに計算して合算する。

    軽減税率(8%)と標準税率(10%)が混在する場合、合計額に一律の率を掛けると
    誤るため、税率別に積み上げる。
    """
    total = Decimal("0")
    for rate, amount in amounts.taxable_by_rate.items():
        total += amount * rate
    return total
