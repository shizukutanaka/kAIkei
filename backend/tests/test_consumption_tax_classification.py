"""消費税の課税区分別集計。

申告書の課税売上・課税仕入は、旧実装では売上・費用の一律80%/20%按分だった。
実際の取引内容と無関係な数値が申告書に載るため、仕訳の税区分から集計する。
"""
from decimal import Decimal

from app.services.consumption_tax_classification import (
    EXEMPT,
    EXPORT,
    NON_TAXABLE,
    TAXABLE,
    classify,
    output_tax,
)


def test_splits_by_tax_type():
    result = classify(
        [
            (TAXABLE, Decimal("0.10"), Decimal("1000")),
            (EXPORT, Decimal("0"), Decimal("200")),
            (NON_TAXABLE, Decimal("0"), Decimal("300")),
            (EXEMPT, Decimal("0"), Decimal("400")),
        ]
    )

    assert result.taxable == Decimal("1000")
    assert result.export == Decimal("200")
    assert result.non_taxable == Decimal("300")
    assert result.exempt == Decimal("400")
    assert result.total == Decimal("1900")


def test_unclassified_lines_are_counted_not_guessed():
    """税区分の無い明細を課税にも非課税にも倒さないこと。

    黙ってどちらかに寄せると、申告額が静かに狂う。
    """
    result = classify(
        [
            (TAXABLE, Decimal("0.10"), Decimal("1000")),
            (None, None, Decimal("500")),
            (None, None, Decimal("250")),
        ]
    )

    assert result.taxable == Decimal("1000")
    assert result.non_taxable == Decimal("0")
    assert result.unclassified == Decimal("750")
    assert result.unclassified_count == 2
    assert result.has_unclassified


def test_unknown_tax_type_is_treated_as_unclassified():
    """新しい区分が増えたときに黙って課税へ倒さないこと。"""
    result = classify([("some_new_type", Decimal("0.10"), Decimal("100"))])

    assert result.taxable == Decimal("0")
    assert result.unclassified == Decimal("100")


def test_no_unclassified_means_no_warning_needed():
    result = classify([(TAXABLE, Decimal("0.10"), Decimal("1000"))])

    assert not result.has_unclassified
    assert result.unclassified_count == 0


def test_sales_total_for_ratio_excludes_out_of_scope():
    """課税売上割合の分母は課税＋免税＋非課税（不課税は入らない）。"""
    result = classify(
        [
            (TAXABLE, Decimal("0.10"), Decimal("1000")),
            (EXPORT, Decimal("0"), Decimal("200")),
            (NON_TAXABLE, Decimal("0"), Decimal("300")),
            (EXEMPT, Decimal("0"), Decimal("999")),
        ]
    )

    assert result.sales_total_for_ratio == Decimal("1500")


def test_output_tax_uses_each_rate():
    """軽減税率と標準税率が混在しても、率ごとに計算すること。

    合計額へ一律10%を掛けると軽減税率分を取りすぎる。
    """
    result = classify(
        [
            (TAXABLE, Decimal("0.10"), Decimal("1000")),
            (TAXABLE, Decimal("0.08"), Decimal("1000")),
        ]
    )

    assert output_tax(result) == Decimal("180.00")
    # 一律10%なら200になってしまう。
    assert output_tax(result) != Decimal("200")


def test_output_tax_is_zero_without_taxable_sales():
    result = classify([(NON_TAXABLE, Decimal("0"), Decimal("1000"))])

    assert output_tax(result) == Decimal("0")


def test_empty_input():
    result = classify([])

    assert result.total == Decimal("0")
    assert not result.has_unclassified
