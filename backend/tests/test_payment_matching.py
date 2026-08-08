"""振込データと銀行出金明細の突合テスト。"""

from datetime import date
from decimal import Decimal

import pytest

from app.schemas.schemas import PaymentMatchingResponse
from app.services.payment_matching import (
    MATCH_AGGREGATE,
    MATCH_EXACT,
    MATCH_FEE_ADJUSTED,
    BankWithdrawal,
    ExpectedPayment,
    PaymentMatchingService,
)


def _payment(payment_id: str, amount: str, day: int = 25, payee: str = "ヤマダ") -> ExpectedPayment:
    return ExpectedPayment(
        payment_id=payment_id,
        payee_name=payee,
        amount=Decimal(amount),
        payment_date=date(2025, 8, day),
    )


def _withdrawal(line_id: str, amount: str, day: int = 25) -> BankWithdrawal:
    return BankWithdrawal(
        line_id=line_id,
        transaction_date=date(2025, 8, day),
        amount=Decimal(amount),
    )


def test_exact_one_to_one_match():
    result = PaymentMatchingService.match(
        withdrawals=[_withdrawal("B1", "100000")],
        payments=[_payment("P1", "100000")],
    )
    assert result.matched_count == 1
    assert result.matches[0].match_type == MATCH_EXACT
    assert result.matches[0].payment_ids == ["P1"]
    assert result.matches[0].difference == Decimal("0")
    assert result.fully_reconciled is True


def test_aggregate_withdrawal_matches_multiple_payments():
    # 総合振込は1本の合算出金として記帳される。
    result = PaymentMatchingService.match(
        withdrawals=[_withdrawal("B1", "349340")],
        payments=[_payment("P1", "100000"), _payment("P2", "249340")],
    )
    assert result.matched_count == 1
    match = result.matches[0]
    assert match.match_type == MATCH_AGGREGATE
    assert sorted(match.payment_ids) == ["P1", "P2"]
    assert match.matched_amount == Decimal("349340")
    assert result.fully_reconciled is True


def test_exact_match_is_taken_before_aggregate():
    # 100,000 の出金は同額の P1 と確定させ、残りを合算突合に回す。
    result = PaymentMatchingService.match(
        withdrawals=[_withdrawal("B1", "100000"), _withdrawal("B2", "150000")],
        payments=[
            _payment("P1", "100000"),
            _payment("P2", "60000"),
            _payment("P3", "90000"),
        ],
    )
    by_line = {match.line_id: match for match in result.matches}
    assert by_line["B1"].payment_ids == ["P1"]
    assert by_line["B1"].match_type == MATCH_EXACT
    assert sorted(by_line["B2"].payment_ids) == ["P2", "P3"]
    assert by_line["B2"].match_type == MATCH_AGGREGATE
    assert result.fully_reconciled is True


def test_fee_difference_matched_only_within_tolerance():
    withdrawals = [_withdrawal("B1", "99340")]
    payments = [_payment("P1", "100000")]

    strict = PaymentMatchingService.match(withdrawals=withdrawals, payments=payments)
    assert strict.matched_count == 0
    assert strict.unmatched_line_ids == ["B1"]
    assert strict.unmatched_payment_ids == ["P1"]

    lenient = PaymentMatchingService.match(
        withdrawals=withdrawals,
        payments=payments,
        fee_tolerance=Decimal("880"),
    )
    assert lenient.matches[0].match_type == MATCH_FEE_ADJUSTED
    assert lenient.matches[0].difference == Decimal("-660")
    assert lenient.fully_reconciled is True


def test_date_outside_tolerance_is_not_matched():
    result = PaymentMatchingService.match(
        withdrawals=[_withdrawal("B1", "100000", day=29)],
        payments=[_payment("P1", "100000", day=25)],
    )
    assert result.matched_count == 0

    within = PaymentMatchingService.match(
        withdrawals=[_withdrawal("B1", "100000", day=28)],
        payments=[_payment("P1", "100000", day=25)],
    )
    assert within.matched_count == 1


def test_ambiguous_same_amount_payments_are_left_for_human():
    # 同額の支払が2件あるとどちらか決められないため自動突合しない。
    result = PaymentMatchingService.match(
        withdrawals=[_withdrawal("B1", "100000")],
        payments=[_payment("P1", "100000"), _payment("P2", "100000", payee="スズキ")],
    )
    assert result.matched_count == 0
    assert result.unmatched_line_ids == ["B1"]
    assert sorted(result.unmatched_payment_ids) == ["P1", "P2"]


def test_payment_is_used_only_once():
    result = PaymentMatchingService.match(
        withdrawals=[_withdrawal("B1", "100000"), _withdrawal("B2", "100000")],
        payments=[_payment("P1", "100000")],
    )
    used = [pid for match in result.matches for pid in match.payment_ids]
    assert used.count("P1") <= 1
    assert result.fully_reconciled is False


def test_unmatched_totals_are_reported():
    result = PaymentMatchingService.match(
        withdrawals=[_withdrawal("B1", "100000"), _withdrawal("B2", "70000")],
        payments=[_payment("P1", "100000"), _payment("P2", "55000")],
    )
    assert result.matched_count == 1
    assert result.matched_amount_total == Decimal("100000")
    assert result.unmatched_withdrawal_total == Decimal("70000")
    assert result.unmatched_payment_total == Decimal("55000")
    assert result.fully_reconciled is False


def test_aggregate_requires_two_or_more_payments():
    # 単独一致は exact 段階で拾うため、合算段階が1件の組合せを作ることはない。
    result = PaymentMatchingService.match(
        withdrawals=[_withdrawal("B1", "100000"), _withdrawal("B2", "100000")],
        payments=[_payment("P1", "100000"), _payment("P2", "100000")],
    )
    assert result.matched_count == 0


def test_duplicate_payment_id_rejected():
    with pytest.raises(ValueError, match="payment_id must be unique"):
        PaymentMatchingService.match(
            withdrawals=[_withdrawal("B1", "100000")],
            payments=[_payment("P1", "100000"), _payment("P1", "200000")],
        )


def test_duplicate_line_id_rejected():
    with pytest.raises(ValueError, match="line_id must be unique"):
        PaymentMatchingService.match(
            withdrawals=[_withdrawal("B1", "100000"), _withdrawal("B1", "200000")],
            payments=[_payment("P1", "100000")],
        )


def test_non_positive_amounts_rejected():
    with pytest.raises(ValueError, match="withdrawal amount must be positive"):
        PaymentMatchingService.match(
            withdrawals=[_withdrawal("B1", "0")],
            payments=[_payment("P1", "100000")],
        )
    with pytest.raises(ValueError, match="payment amount must be positive"):
        PaymentMatchingService.match(
            withdrawals=[_withdrawal("B1", "100000")],
            payments=[_payment("P1", "-1")],
        )


def test_negative_tolerances_rejected():
    with pytest.raises(ValueError, match="date_tolerance_days"):
        PaymentMatchingService.match(
            withdrawals=[_withdrawal("B1", "100000")],
            payments=[_payment("P1", "100000")],
            date_tolerance_days=-1,
        )
    with pytest.raises(ValueError, match="fee_tolerance"):
        PaymentMatchingService.match(
            withdrawals=[_withdrawal("B1", "100000")],
            payments=[_payment("P1", "100000")],
            fee_tolerance=Decimal("-1"),
        )


def test_empty_input_is_fully_reconciled():
    result = PaymentMatchingService.match(withdrawals=[], payments=[])
    assert result.matched_count == 0
    assert result.fully_reconciled is True


def test_response_schema_serializes_dataclass():
    result = PaymentMatchingService.match(
        withdrawals=[_withdrawal("B1", "349340")],
        payments=[_payment("P1", "100000"), _payment("P2", "249340")],
    )
    response = PaymentMatchingResponse.model_validate(result)
    assert response.matches[0].match_type == MATCH_AGGREGATE
    assert response.matched_amount_total == Decimal("349340")
    assert response.fully_reconciled is True
