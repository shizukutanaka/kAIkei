import pytest

from app.services.denchou_scanner import (
    INPUT_PERIOD_BUSINESS_CYCLE,
    INPUT_PERIOD_PROMPT,
    DenchouScannerService,
)


def _base_kwargs(**overrides):
    kwargs = dict(
        resolution_dpi=200,
        is_color=True,
        is_general_document=False,
        input_period_type=INPUT_PERIOD_PROMPT,
        days_until_input=3,
        has_operational_rules=False,
        has_timestamp=True,
        has_correction_deletion_history=False,
        has_display_device=True,
        can_search_by_date=True,
        can_search_by_amount=True,
        can_search_by_counterparty=True,
        can_search_by_range=True,
        can_search_by_combination=True,
    )
    kwargs.update(overrides)
    return kwargs


def test_full_compliance():
    result = DenchouScannerService.check(**_base_kwargs())
    assert result.compliant is True
    assert result.missing_requirements == ()


def test_low_resolution():
    result = DenchouScannerService.check(**_base_kwargs(resolution_dpi=150))
    assert result.resolution_met is False
    assert "resolution" in result.missing_requirements
    assert result.compliant is False


def test_important_document_requires_color():
    result = DenchouScannerService.check(**_base_kwargs(is_color=False))
    assert result.color_met is False
    assert "color" in result.missing_requirements


def test_general_document_allows_grayscale():
    result = DenchouScannerService.check(**_base_kwargs(is_color=False, is_general_document=True))
    assert result.color_met is True


def test_prompt_period_exceeded():
    result = DenchouScannerService.check(**_base_kwargs(days_until_input=8))
    assert result.input_period_met is False
    assert "input_period" in result.missing_requirements


def test_business_cycle_requires_rules():
    without_rules = DenchouScannerService.check(
        **_base_kwargs(input_period_type=INPUT_PERIOD_BUSINESS_CYCLE, days_until_input=40)
    )
    assert without_rules.input_period_met is False

    with_rules = DenchouScannerService.check(
        **_base_kwargs(
            input_period_type=INPUT_PERIOD_BUSINESS_CYCLE,
            days_until_input=40,
            has_operational_rules=True,
        )
    )
    assert with_rules.input_period_met is True


def test_business_cycle_over_limit():
    result = DenchouScannerService.check(
        **_base_kwargs(
            input_period_type=INPUT_PERIOD_BUSINESS_CYCLE,
            days_until_input=68,
            has_operational_rules=True,
        )
    )
    assert result.input_period_met is False


def test_authenticity_missing():
    result = DenchouScannerService.check(**_base_kwargs(has_timestamp=False))
    assert result.authenticity_met is False
    assert "authenticity" in result.missing_requirements


def test_correction_history_satisfies_authenticity():
    result = DenchouScannerService.check(
        **_base_kwargs(has_timestamp=False, has_correction_deletion_history=True)
    )
    assert result.authenticity_met is True


def test_search_incomplete():
    result = DenchouScannerService.check(**_base_kwargs(can_search_by_combination=False))
    assert result.visibility_met is False
    assert "search" in result.missing_requirements


def test_invalid_resolution_raises():
    with pytest.raises(ValueError):
        DenchouScannerService.check(**_base_kwargs(resolution_dpi=0))


def test_invalid_period_type_raises():
    with pytest.raises(ValueError):
        DenchouScannerService.check(**_base_kwargs(input_period_type="unknown"))
