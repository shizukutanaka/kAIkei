"""滞留債権の貸倒判定(貸倒損失・個別評価・一括評価)のテスト。"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.bad_debt_assessment import (
    EVENT_BANKRUPTCY_FILING,
    EVENT_BILL_SUSPENSION,
    EVENT_DEBT_FORGIVENESS,
    EVENT_DEFERRED_PAYMENT,
    EVENT_INSOLVENCY,
    EVENT_REHABILITATION_PLAN,
    TREATMENT_BAD_DEBT_LOSS,
    TREATMENT_GENERAL_RESERVE,
    TREATMENT_INDIVIDUAL_RESERVE,
    TREATMENT_MANUAL,
    BadDebtAssessmentService,
    DebtorReceivable,
)

AS_OF = date(2025, 3, 31)


def _receivable(**overrides: object) -> DebtorReceivable:
    base = {
        "receivable_id": "R1",
        "customer_code": "C1",
        "customer_name": "山田商事",
        "amount": Decimal("1000000"),
        "due_date": date(2024, 6, 30),
    }
    base.update(overrides)
    return DebtorReceivable(**base)  # type: ignore[arg-type]


def _assess(*receivables: DebtorReceivable, industry: str = "wholesale_retail"):
    return BadDebtAssessmentService.assess(
        as_of=AS_OF,
        receivables=list(receivables),
        industry=industry,
    )


def test_legal_write_off_is_bad_debt_loss() -> None:
    result = _assess(
        _receivable(
            event=EVENT_REHABILITATION_PLAN,
            event_date=date(2025, 2, 1),
            written_off_amount=Decimal("1000000"),
        ),
    )
    item = result.items[0]
    assert item.treatment == TREATMENT_BAD_DEBT_LOSS
    assert item.basis == "9-6-1"
    assert item.loss_amount == Decimal("1000000")
    assert result.total_loss == Decimal("1000000")


def test_partial_write_off_leaves_remainder_to_manual() -> None:
    result = _assess(
        _receivable(
            event=EVENT_DEBT_FORGIVENESS,
            written_off_amount=Decimal("600000"),
        ),
    )
    item = result.items[0]
    assert item.treatment == TREATMENT_MANUAL
    assert item.loss_amount == Decimal("600000")
    assert result.manual_receivable_ids == ["R1"]
    # 残額を勝手に一括評価へ回さない
    assert result.general_receivables == Decimal("0")


def test_write_off_event_requires_amount() -> None:
    with pytest.raises(ValueError, match="written_off_amount"):
        _assess(_receivable(event=EVENT_REHABILITATION_PLAN))


def test_factual_loss_when_fully_unrecoverable() -> None:
    result = _assess(_receivable(unrecoverable=True))
    item = result.items[0]
    assert item.treatment == TREATMENT_BAD_DEBT_LOSS
    assert item.basis == "9-6-2"
    assert item.loss_amount == Decimal("1000000")


def test_secured_unrecoverable_receivable_requires_manual() -> None:
    """担保物があるときは処分後でなければ事実上の貸倒れを計上できない。"""
    result = _assess(_receivable(unrecoverable=True, secured_amount=Decimal("300000")))
    item = result.items[0]
    assert item.treatment == TREATMENT_MANUAL
    assert item.loss_amount == Decimal("0")
    assert result.total_loss == Decimal("0")


def test_trade_suspension_over_one_year_leaves_memorandum_value() -> None:
    result = _assess(
        _receivable(
            due_date=date(2024, 1, 31),
            last_transaction_date=date(2024, 1, 31),
        ),
    )
    item = result.items[0]
    assert item.treatment == TREATMENT_BAD_DEBT_LOSS
    assert item.basis == "9-6-3"
    assert item.loss_amount == Decimal("999999")  # 備忘価額1円を残す


def test_trade_suspension_under_one_year_is_general() -> None:
    result = _assess(
        _receivable(
            due_date=date(2024, 6, 30),
            last_transaction_date=date(2024, 6, 30),
        ),
    )
    assert result.items[0].treatment == TREATMENT_GENERAL_RESERVE


def test_trade_suspension_measured_from_later_of_due_date() -> None:
    """取引停止が1年以上前でも、期日が1年以内なら貸倒れにできない。"""
    result = _assess(
        _receivable(
            due_date=date(2024, 12, 31),
            last_transaction_date=date(2023, 12, 31),
        ),
    )
    assert result.items[0].treatment == TREATMENT_GENERAL_RESERVE


def test_trade_suspension_not_applied_to_non_trade_receivable() -> None:
    result = _assess(
        _receivable(
            due_date=date(2024, 1, 31),
            last_transaction_date=date(2024, 1, 31),
            is_trade_receivable=False,
        ),
    )
    assert result.items[0].treatment == TREATMENT_GENERAL_RESERVE


def test_formal_criteria_is_half_after_deductions() -> None:
    result = _assess(
        _receivable(
            event=EVENT_BANKRUPTCY_FILING,
            event_date=date(2025, 1, 20),
            secured_amount=Decimal("200000"),
            offsettable_amount=Decimal("100000"),
        ),
    )
    item = result.items[0]
    assert item.treatment == TREATMENT_INDIVIDUAL_RESERVE
    assert item.basis == "令96条1項3号"
    assert item.reserve_limit == Decimal("350000")  # (100万-20万-10万)×50%


def test_bill_suspension_is_formal_criteria() -> None:
    result = _assess(_receivable(event=EVENT_BILL_SUSPENSION))
    assert result.items[0].reserve_limit == Decimal("500000")


def test_insolvency_reserves_full_uncollectible_amount() -> None:
    result = _assess(
        _receivable(event=EVENT_INSOLVENCY, secured_amount=Decimal("400000")),
    )
    item = result.items[0]
    assert item.basis == "令96条1項2号"
    assert item.reserve_limit == Decimal("600000")


def test_deferred_payment_excludes_repayment_within_5years() -> None:
    result = _assess(
        _receivable(
            event=EVENT_DEFERRED_PAYMENT,
            repayment_within_5years=Decimal("400000"),
            secured_amount=Decimal("100000"),
        ),
    )
    item = result.items[0]
    assert item.basis == "令96条1項1号"
    assert item.reserve_limit == Decimal("500000")


def test_secured_amount_can_not_exceed_amount() -> None:
    with pytest.raises(ValueError, match="secured_amount"):
        _assess(_receivable(event=EVENT_INSOLVENCY, secured_amount=Decimal("2000000")))


def test_general_receivables_feed_statutory_rate_reserve() -> None:
    result = _assess(
        _receivable(receivable_id="R1", amount=Decimal("3000000")),
        _receivable(
            receivable_id="R2",
            customer_code="C2",
            amount=Decimal("2000000"),
            offsettable_amount=Decimal("500000"),
        ),
    )
    assert result.general_receivables == Decimal("5000000")
    assert result.general_offsettable == Decimal("500000")
    assert result.general_reserve is not None
    assert result.general_reserve.base_amount == Decimal("4500000")
    assert result.general_reserve.reserve_limit == Decimal("45000")  # 卸売 10/1000
    assert result.total_reserve_limit == Decimal("45000")


def test_individually_assessed_receivable_is_excluded_from_general_base() -> None:
    """同じ債権を個別評価と一括評価で二重に引き当てない。"""
    result = _assess(
        _receivable(receivable_id="R1", amount=Decimal("3000000")),
        _receivable(
            receivable_id="R2",
            customer_code="C2",
            amount=Decimal("2000000"),
            offsettable_amount=Decimal("500000"),
            event=EVENT_BANKRUPTCY_FILING,
        ),
    )
    assert result.general_receivables == Decimal("3000000")
    assert result.general_offsettable == Decimal("0")
    assert result.total_individual_reserve == Decimal("750000")
    assert result.total_reserve_limit == Decimal("780000")  # 750,000 + 30,000


def test_no_general_receivable_yields_no_general_reserve() -> None:
    result = _assess(_receivable(event=EVENT_INSOLVENCY))
    assert result.general_reserve is None
    assert result.total_reserve_limit == Decimal("1000000")


def test_duplicate_receivable_id_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        _assess(_receivable(), _receivable())


def test_unknown_event_rejected() -> None:
    with pytest.raises(ValueError, match="無効な貸倒事由"):
        _assess(_receivable(event="unknown"))


def test_non_positive_amount_rejected() -> None:
    with pytest.raises(ValueError, match="amount must be positive"):
        _assess(_receivable(amount=Decimal("0")))


def test_empty_input() -> None:
    result = _assess()
    assert result.items == []
    assert result.total_loss == Decimal("0")
    assert result.total_reserve_limit == Decimal("0")
    assert result.general_reserve is None


def test_response_schema_serializes_dataclass() -> None:
    from app.schemas.schemas import BadDebtAssessmentResponse

    result = _assess(
        _receivable(),
        _receivable(receivable_id="R2", customer_code="C2", event=EVENT_INSOLVENCY),
    )
    response = BadDebtAssessmentResponse.model_validate(result)
    assert response.general_reserve is not None
    assert len(response.items) == 2
