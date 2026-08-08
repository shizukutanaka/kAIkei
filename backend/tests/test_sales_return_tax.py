from decimal import Decimal

import pytest

from app.schemas.schemas import SalesReturnTaxResponse
from app.services.sales_return_tax import SalesReturnLine, SalesReturnTaxService


def test_response_schema_validates_service_result():
    """SalesReturnTaxResponse.model_validate must accept the service dataclass
    (regression: response schema needs from_attributes to serialize the result)."""
    result = SalesReturnTaxService.compute(
        [
            SalesReturnLine(amount=Decimal("110000"), tax_rate=Decimal("0.10")),
            SalesReturnLine(amount=Decimal("108000"), tax_rate=Decimal("0.08")),
        ]
    )
    response = SalesReturnTaxResponse.model_validate(result)
    assert response.total_deductible_tax == Decimal("18000")
    assert [b.tax_rate for b in response.by_rate] == [Decimal("0.08"), Decimal("0.10")]


def test_single_standard_rate():
    result = SalesReturnTaxService.compute(
        [SalesReturnLine(amount=Decimal("110000"), tax_rate=Decimal("0.10"))]
    )
    assert result.total_return == Decimal("110000")
    assert result.total_deductible_tax == Decimal("10000")
    assert len(result.by_rate) == 1


def test_mixed_rates_sorted():
    result = SalesReturnTaxService.compute(
        [
            SalesReturnLine(amount=Decimal("110000"), tax_rate=Decimal("0.10")),
            SalesReturnLine(amount=Decimal("108000"), tax_rate=Decimal("0.08")),
        ]
    )
    assert [b.tax_rate for b in result.by_rate] == [Decimal("0.08"), Decimal("0.10")]
    assert result.by_rate[0].deductible_tax == Decimal("8000")
    assert result.by_rate[1].deductible_tax == Decimal("10000")
    assert result.total_return == Decimal("218000")
    assert result.total_deductible_tax == Decimal("18000")


def test_same_rate_aggregated_before_extraction():
    result = SalesReturnTaxService.compute(
        [
            SalesReturnLine(amount=Decimal("100"), tax_rate=Decimal("0.10")),
            SalesReturnLine(amount=Decimal("100"), tax_rate=Decimal("0.10")),
        ]
    )
    assert len(result.by_rate) == 1
    assert result.by_rate[0].return_amount == Decimal("200")
    # 200*0.1/1.1 = 18.18 -> 18
    assert result.total_deductible_tax == Decimal("18")


def test_empty_raises():
    with pytest.raises(ValueError):
        SalesReturnTaxService.compute([])


def test_unsupported_rate_raises():
    with pytest.raises(ValueError):
        SalesReturnTaxService.compute(
            [SalesReturnLine(amount=Decimal("1000"), tax_rate=Decimal("0.05"))]
        )


def test_negative_amount_raises():
    with pytest.raises(ValueError):
        SalesReturnTaxService.compute(
            [SalesReturnLine(amount=Decimal("-1"), tax_rate=Decimal("0.10"))]
        )
