"""与信限度額チェック(受注可否・与信停止・一時増枠)のテスト。"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.credit_limit import (
    JUDGMENT_APPROVED,
    JUDGMENT_BLOCKED,
    JUDGMENT_MANUAL,
    JUDGMENT_REJECTED,
    JUDGMENT_WARNING,
    CreditLimitService,
    CreditRequest,
)

AS_OF = date(2025, 9, 30)


def _request(**overrides: object) -> CreditRequest:
    base = {
        "customer_code": "C1",
        "customer_name": "山田商事",
        "credit_limit": Decimal("1000000"),
        "receivable_balance": Decimal("400000"),
        "order_amount": Decimal("100000"),
    }
    base.update(overrides)
    return CreditRequest(**base)  # type: ignore[arg-type]


def _check(*requests: CreditRequest, **kwargs: object):
    return CreditLimitService.check(as_of=AS_OF, requests=list(requests), **kwargs)  # type: ignore[arg-type]


def test_order_within_limit_is_approved() -> None:
    result = _check(_request())
    judgment = result.judgments[0]
    assert judgment.judgment == JUDGMENT_APPROVED
    assert judgment.exposure == Decimal("400000")
    assert judgment.available_credit == Decimal("600000")
    assert judgment.exposure_after_order == Decimal("500000")
    assert judgment.excess_amount == Decimal("0")
    assert judgment.utilization_ratio == Decimal("0.5")


def test_order_backlog_and_notes_count_towards_exposure() -> None:
    """受注残を無視すると出荷・請求した瞬間に必ず枠を超える受注を通してしまう。"""
    result = _check(
        _request(
            order_backlog=Decimal("300000"),
            notes_receivable=Decimal("200000"),
            order_amount=Decimal("200000"),
        ),
    )
    judgment = result.judgments[0]
    assert judgment.exposure == Decimal("900000")
    assert judgment.judgment == JUDGMENT_REJECTED
    assert judgment.excess_amount == Decimal("100000")


def test_advance_received_reduces_exposure() -> None:
    result = _check(
        _request(
            receivable_balance=Decimal("900000"),
            advance_received=Decimal("400000"),
            order_amount=Decimal("100000"),
        ),
    )
    assert result.judgments[0].exposure == Decimal("500000")
    assert result.judgments[0].judgment == JUDGMENT_APPROVED


def test_high_utilization_is_warning_not_rejection() -> None:
    result = _check(_request(receivable_balance=Decimal("800000")))
    judgment = result.judgments[0]
    assert judgment.judgment == JUDGMENT_WARNING
    assert judgment.utilization_ratio == Decimal("0.9")


def test_warning_ratio_boundary_is_inclusive() -> None:
    result = _check(_request(receivable_balance=Decimal("700000")))
    assert result.judgments[0].utilization_ratio == Decimal("0.8")
    assert result.judgments[0].judgment == JUDGMENT_WARNING


def test_exactly_at_limit_is_not_rejected() -> None:
    result = _check(_request(receivable_balance=Decimal("900000")))
    judgment = result.judgments[0]
    assert judgment.exposure_after_order == Decimal("1000000")
    assert judgment.judgment == JUDGMENT_WARNING
    assert judgment.excess_amount == Decimal("0")


def test_overdue_customer_is_blocked_even_with_available_credit() -> None:
    """回収が遅れている相手への出荷継続が貸倒れの典型的な発生経路。"""
    result = _check(_request(max_days_overdue=61))
    judgment = result.judgments[0]
    assert judgment.judgment == JUDGMENT_BLOCKED
    assert judgment.available_credit == Decimal("600000")
    assert result.blocked_customer_codes == ["C1"]


def test_overdue_below_threshold_is_not_blocked() -> None:
    result = _check(_request(max_days_overdue=60))
    assert result.judgments[0].judgment == JUDGMENT_APPROVED


def test_blocking_threshold_is_configurable() -> None:
    result = _check(_request(max_days_overdue=31), blocking_days_overdue=31)
    assert result.judgments[0].judgment == JUDGMENT_BLOCKED


def test_default_event_blocks_regardless_of_overdue_days() -> None:
    result = _check(_request(has_default_event=True, max_days_overdue=0))
    judgment = result.judgments[0]
    assert judgment.judgment == JUDGMENT_BLOCKED
    assert "貸倒事由" in judgment.reason


def test_missing_credit_limit_requires_manual_judgment() -> None:
    result = _check(_request(credit_limit=None))
    judgment = result.judgments[0]
    assert judgment.judgment == JUDGMENT_MANUAL
    assert judgment.utilization_ratio is None
    assert result.manual_customer_codes == ["C1"]


def test_zero_credit_limit_rejects_any_order() -> None:
    result = _check(_request(credit_limit=Decimal("0")))
    assert result.judgments[0].judgment == JUDGMENT_REJECTED


def test_valid_temporary_limit_extends_credit_line() -> None:
    result = _check(
        _request(
            receivable_balance=Decimal("1000000"),
            order_amount=Decimal("200000"),
            temporary_limit=Decimal("500000"),
            temporary_limit_expiry=date(2025, 9, 30),
        ),
    )
    judgment = result.judgments[0]
    assert judgment.credit_line == Decimal("1500000")
    assert judgment.judgment == JUDGMENT_WARNING


def test_expired_temporary_limit_is_ignored() -> None:
    result = _check(
        _request(
            receivable_balance=Decimal("1000000"),
            order_amount=Decimal("200000"),
            temporary_limit=Decimal("500000"),
            temporary_limit_expiry=date(2025, 9, 29),
        ),
    )
    judgment = result.judgments[0]
    assert judgment.credit_line == Decimal("1000000")
    assert judgment.judgment == JUDGMENT_REJECTED
    assert judgment.excess_amount == Decimal("200000")


def test_temporary_limit_requires_expiry() -> None:
    with pytest.raises(ValueError, match="temporary_limit_expiry"):
        _check(_request(temporary_limit=Decimal("100000")))


def test_totals_and_grouping_across_customers() -> None:
    result = _check(
        _request(customer_code="C1"),
        _request(customer_code="C2", receivable_balance=Decimal("1200000")),
        _request(customer_code="C3", max_days_overdue=90),
        _request(customer_code="C4", credit_limit=None),
    )
    assert result.total_exposure == Decimal("2400000")
    # 与信余力は超過分(C2)や限度額未設定(C4)をマイナス計上しない
    assert result.total_available_credit == Decimal("1200000")
    assert result.rejected_customer_codes == ["C2"]
    assert result.blocked_customer_codes == ["C3"]
    assert result.manual_customer_codes == ["C4"]


def test_duplicate_customer_code_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        _check(_request(), _request())


def test_negative_amount_rejected() -> None:
    with pytest.raises(ValueError, match="receivable_balance"):
        _check(_request(receivable_balance=Decimal("-1")))


def test_invalid_warning_ratio_rejected() -> None:
    with pytest.raises(ValueError, match="warning_ratio"):
        _check(_request(), warning_ratio=Decimal("1.5"))


def test_invalid_blocking_days_rejected() -> None:
    with pytest.raises(ValueError, match="blocking_days_overdue"):
        _check(_request(), blocking_days_overdue=0)


def test_empty_input() -> None:
    result = _check()
    assert result.judgments == []
    assert result.total_exposure == Decimal("0")
    assert result.total_available_credit == Decimal("0")


def test_response_schema_serializes_dataclass() -> None:
    from app.schemas.schemas import CreditCheckResponse

    result = _check(_request(), _request(customer_code="C2", credit_limit=None))
    response = CreditCheckResponse.model_validate(result)
    assert len(response.judgments) == 2
    assert response.judgments[1].utilization_ratio is None
