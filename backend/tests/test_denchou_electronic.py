from decimal import Decimal

import pytest

from app.services.denchou_electronic import (
    SEARCH_LEVEL_FULL,
    SEARCH_LEVEL_THREE_ITEMS_ONLY,
    SEARCH_LEVEL_WAIVED,
    DenchouElectronicService,
)


def _base_kwargs(**overrides):
    kwargs = dict(
        has_timestamp=False,
        has_correction_deletion_history=False,
        has_operational_rules=False,
        has_display_device=True,
        can_search_by_date=True,
        can_search_by_amount=True,
        can_search_by_counterparty=True,
        can_search_by_range=True,
        can_search_by_combination=True,
        base_period_sales=Decimal("100000000"),
        can_provide_download=False,
    )
    kwargs.update(overrides)
    return kwargs


def test_full_compliance_with_operational_rules():
    result = DenchouElectronicService.check(**_base_kwargs(has_operational_rules=True))
    assert result.authenticity_met is True
    assert result.required_search_level == SEARCH_LEVEL_FULL
    assert result.compliant is True
    assert result.missing_requirements == ()


def test_authenticity_missing():
    result = DenchouElectronicService.check(**_base_kwargs())
    assert result.authenticity_met is False
    assert result.compliant is False
    assert "authenticity" in result.missing_requirements


def test_full_level_requires_range_and_combination():
    result = DenchouElectronicService.check(
        **_base_kwargs(has_timestamp=True, can_search_by_range=False)
    )
    assert result.required_search_level == SEARCH_LEVEL_FULL
    assert result.search_requirement_met is False
    assert "search" in result.missing_requirements


def test_download_available_needs_only_three_items():
    result = DenchouElectronicService.check(
        **_base_kwargs(
            has_timestamp=True,
            can_provide_download=True,
            can_search_by_range=False,
            can_search_by_combination=False,
        )
    )
    assert result.required_search_level == SEARCH_LEVEL_THREE_ITEMS_ONLY
    assert result.search_requirement_met is True
    assert result.compliant is True


def test_small_business_search_waived():
    result = DenchouElectronicService.check(
        **_base_kwargs(
            has_timestamp=True,
            base_period_sales=Decimal("50000000"),
            can_provide_download=True,
            can_search_by_date=False,
            can_search_by_amount=False,
            can_search_by_counterparty=False,
            can_search_by_range=False,
            can_search_by_combination=False,
        )
    )
    assert result.required_search_level == SEARCH_LEVEL_WAIVED
    assert result.search_requirement_met is True
    assert result.compliant is True


def test_over_threshold_not_waived():
    result = DenchouElectronicService.check(
        **_base_kwargs(
            has_timestamp=True,
            base_period_sales=Decimal("50000001"),
            can_provide_download=True,
            can_search_by_range=False,
            can_search_by_combination=False,
        )
    )
    assert result.required_search_level == SEARCH_LEVEL_THREE_ITEMS_ONLY


def test_missing_display_device():
    result = DenchouElectronicService.check(
        **_base_kwargs(has_timestamp=True, has_display_device=False)
    )
    assert result.visibility_met is False
    assert "display_device" in result.missing_requirements
    assert result.compliant is False


def test_negative_sales_raises():
    with pytest.raises(ValueError):
        DenchouElectronicService.check(**_base_kwargs(base_period_sales=Decimal("-1")))
