"""貸倒仕訳ドラフト(引当金取崩・消費税39条・繰入/戻入)のテスト。"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.bad_debt_assessment import (
    EVENT_INSOLVENCY,
    BadDebtAssessmentService,
    DebtorReceivable,
)
from app.services.bad_debt_journal_draft import (
    DRAFT_ALLOWANCE_PROVISION,
    DRAFT_ALLOWANCE_REVERSAL,
    DRAFT_WRITE_OFF,
    METHOD_REVERSAL,
    ROLE_ACCOUNTS_RECEIVABLE,
    ROLE_BAD_DEBT_ALLOWANCE,
    ROLE_BAD_DEBT_LOSS,
    ROLE_CONSUMPTION_TAX_RECEIVED,
    TAX_INCLUSIVE,
    BadDebtJournalDraftService,
)

AS_OF = date(2025, 3, 31)
TXN = date(2025, 3, 31)


def _receivable(**overrides: object) -> DebtorReceivable:
    base = {
        "receivable_id": "R1",
        "customer_code": "C1",
        "customer_name": "回収不能社",
        "amount": Decimal("1100000"),
        "due_date": date(2024, 6, 30),
        "unrecoverable": True,
    }
    base.update(overrides)
    return DebtorReceivable(**base)  # type: ignore[arg-type]


def _generate(*receivables: DebtorReceivable, industry: str = "wholesale_retail", **kwargs: object):
    assessment = BadDebtAssessmentService.assess(
        as_of=AS_OF,
        receivables=list(receivables),
        industry=industry,
    )
    return BadDebtJournalDraftService.generate(
        assessment,
        transaction_date=TXN,
        **kwargs,  # type: ignore[arg-type]
    )


def _line(draft, role: str) -> Decimal:
    return sum(
        (line.debit + line.credit for line in draft.lines if line.account_role == role),
        Decimal("0"),
    )


def test_write_off_splits_consumption_tax_under_exclusive_method() -> None:
    result = _generate(_receivable())
    draft = result.drafts[0]
    assert draft.draft_type == DRAFT_WRITE_OFF
    assert _line(draft, ROLE_ACCOUNTS_RECEIVABLE) == Decimal("1100000")
    assert _line(draft, ROLE_CONSUMPTION_TAX_RECEIVED) == Decimal("100000")
    assert _line(draft, ROLE_BAD_DEBT_LOSS) == Decimal("1000000")
    assert result.total_consumption_tax_deduction == Decimal("100000")
    assert result.balanced


def test_inclusive_method_keeps_tax_in_loss_but_still_reports_deduction() -> None:
    result = _generate(_receivable(), tax_treatment=TAX_INCLUSIVE)
    draft = result.drafts[0]
    assert _line(draft, ROLE_CONSUMPTION_TAX_RECEIVED) == Decimal("0")
    assert _line(draft, ROLE_BAD_DEBT_LOSS) == Decimal("1100000")
    # 申告上の控除税額は経理方式に関わらず同額
    assert result.total_consumption_tax_deduction == Decimal("100000")


def test_reduced_rate_receivable() -> None:
    result = _generate(
        _receivable(amount=Decimal("1080000")),
        tax_rates={"R1": Decimal("0.08")},
    )
    assert result.total_consumption_tax_deduction == Decimal("80000")
    assert result.total_loss_expense == Decimal("1000000")


def test_zero_rate_receivable_has_no_tax_deduction() -> None:
    """課税資産の譲渡等に係る債権でなければ39条の控除はできない。"""
    result = _generate(_receivable(), tax_rates={"R1": Decimal("0")})
    assert result.total_consumption_tax_deduction == Decimal("0")
    assert result.total_loss_expense == Decimal("1100000")


def test_allowance_is_used_before_loss() -> None:
    result = _generate(_receivable(), allowance_balance=Decimal("400000"))
    draft = result.drafts[0]
    assert _line(draft, ROLE_BAD_DEBT_ALLOWANCE) == Decimal("400000")
    assert _line(draft, ROLE_BAD_DEBT_LOSS) == Decimal("600000")
    assert result.total_allowance_used == Decimal("400000")
    assert result.allowance_after_write_off == Decimal("0")


def test_allowance_exceeding_write_off_still_books_consumption_tax() -> None:
    result = _generate(_receivable(), allowance_balance=Decimal("2000000"))
    draft = result.drafts[0]
    assert _line(draft, ROLE_BAD_DEBT_ALLOWANCE) == Decimal("1000000")
    assert _line(draft, ROLE_CONSUMPTION_TAX_RECEIVED) == Decimal("100000")
    assert _line(draft, ROLE_BAD_DEBT_LOSS) == Decimal("0")
    assert result.allowance_after_write_off == Decimal("1000000")
    assert result.balanced


def test_allowance_applied_across_multiple_write_offs_in_order() -> None:
    result = _generate(
        _receivable(receivable_id="R1", amount=Decimal("1100000")),
        _receivable(receivable_id="R2", customer_code="C2", amount=Decimal("550000")),
        allowance_balance=Decimal("1200000"),
    )
    first, second = result.drafts[0], result.drafts[1]
    assert _line(first, ROLE_BAD_DEBT_ALLOWANCE) == Decimal("1000000")  # 税額分は残す
    assert _line(second, ROLE_BAD_DEBT_ALLOWANCE) == Decimal("200000")
    assert _line(second, ROLE_BAD_DEBT_LOSS) == Decimal("300000")
    assert result.allowance_after_write_off == Decimal("0")


def test_difference_method_provisions_only_the_shortfall() -> None:
    result = _generate(
        _receivable(receivable_id="R2", customer_code="C2", unrecoverable=False, event=EVENT_INSOLVENCY),
        allowance_balance=Decimal("400000"),
    )
    # 目標 1,100,000 − 残高 400,000 = 700,000 のみ繰入
    assert result.allowance_target == Decimal("1100000")
    assert result.provision_amount == Decimal("700000")
    assert result.reversal_amount == Decimal("0")
    assert result.allowance_closing_balance == Decimal("1100000")
    assert [draft.draft_type for draft in result.drafts] == [DRAFT_ALLOWANCE_PROVISION]


def test_difference_method_reverses_excess_allowance() -> None:
    result = _generate(
        _receivable(receivable_id="R2", customer_code="C2", unrecoverable=False, event=EVENT_INSOLVENCY),
        allowance_balance=Decimal("1500000"),
    )
    assert result.provision_amount == Decimal("0")
    assert result.reversal_amount == Decimal("400000")
    assert result.allowance_closing_balance == Decimal("1100000")
    assert [draft.draft_type for draft in result.drafts] == [DRAFT_ALLOWANCE_REVERSAL]


def test_reversal_method_books_both_sides_gross() -> None:
    result = _generate(
        _receivable(receivable_id="R2", customer_code="C2", unrecoverable=False, event=EVENT_INSOLVENCY),
        allowance_balance=Decimal("400000"),
        allowance_method=METHOD_REVERSAL,
    )
    assert result.reversal_amount == Decimal("400000")
    assert result.provision_amount == Decimal("1100000")
    assert result.allowance_closing_balance == Decimal("1100000")
    assert [draft.draft_type for draft in result.drafts] == [
        DRAFT_ALLOWANCE_REVERSAL,
        DRAFT_ALLOWANCE_PROVISION,
    ]


def test_write_off_and_provision_in_one_run() -> None:
    result = _generate(
        _receivable(receivable_id="R1", amount=Decimal("1100000")),
        _receivable(
            receivable_id="R2",
            customer_code="C2",
            amount=Decimal("2000000"),
            unrecoverable=False,
        ),
        allowance_balance=Decimal("300000"),
    )
    assert result.total_write_off == Decimal("1100000")
    assert result.total_allowance_used == Decimal("300000")
    assert result.total_loss_expense == Decimal("700000")
    assert result.allowance_target == Decimal("20000")  # 2,000,000 × 10/1000
    assert result.provision_amount == Decimal("20000")
    assert result.balanced


def test_receivables_without_loss_generate_no_write_off_draft() -> None:
    result = _generate(
        _receivable(receivable_id="R2", customer_code="C2", unrecoverable=False),
    )
    assert all(draft.draft_type != DRAFT_WRITE_OFF for draft in result.drafts)
    assert result.total_write_off == Decimal("0")


def test_negative_allowance_balance_rejected() -> None:
    with pytest.raises(ValueError, match="allowance_balance"):
        _generate(_receivable(), allowance_balance=Decimal("-1"))


def test_unknown_tax_treatment_rejected() -> None:
    with pytest.raises(ValueError, match="無効な経理方式"):
        _generate(_receivable(), tax_treatment="foo")


def test_unknown_allowance_method_rejected() -> None:
    with pytest.raises(ValueError, match="無効な引当金の計上方法"):
        _generate(_receivable(), allowance_method="foo")


def test_tax_rate_for_unknown_receivable_rejected() -> None:
    with pytest.raises(ValueError, match="存在しない債権"):
        _generate(_receivable(), tax_rates={"XX": Decimal("0.10")})


def test_unsupported_tax_rate_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported tax_rate"):
        _generate(_receivable(), tax_rates={"R1": Decimal("0.05")})


def test_empty_assessment_produces_no_drafts() -> None:
    result = _generate()
    assert result.drafts == []
    assert result.allowance_closing_balance == Decimal("0")
    assert result.balanced


def test_response_schema_serializes_dataclass() -> None:
    from app.schemas.schemas import BadDebtJournalResponse

    result = _generate(_receivable(), allowance_balance=Decimal("400000"))
    response = BadDebtJournalResponse.model_validate(result)
    assert response.drafts[0].lines
    assert response.balanced
