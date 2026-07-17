from decimal import Decimal

import pytest

from app.services.approval_policy import (
    ApprovalPolicySpec,
    policy_applies,
    required_approval_steps,
    select_policies,
)


def _spec(policy_id, doc="expense", role="approver", step=1, lo=None, hi=None):
    return ApprovalPolicySpec(
        policy_id=policy_id,
        document_type=doc,
        approver_role=role,
        step_order=step,
        min_amount=Decimal(lo) if lo is not None else None,
        max_amount=Decimal(hi) if hi is not None else None,
    )


class TestPolicyApplies:
    def test_document_type_must_match(self):
        assert policy_applies(_spec("p", doc="expense"), "invoice", Decimal("100")) is False

    def test_within_amount_range(self):
        spec = _spec("p", lo="1000", hi="100000")
        assert policy_applies(spec, "expense", Decimal("50000")) is True

    def test_below_min_excluded(self):
        spec = _spec("p", lo="1000")
        assert policy_applies(spec, "expense", Decimal("500")) is False

    def test_above_max_excluded(self):
        spec = _spec("p", hi="100000")
        assert policy_applies(spec, "expense", Decimal("100001")) is False

    def test_open_ended_range(self):
        spec = _spec("p")  # no min/max
        assert policy_applies(spec, "expense", Decimal("0")) is True
        assert policy_applies(spec, "expense", Decimal("99999999")) is True

    def test_boundaries_inclusive(self):
        spec = _spec("p", lo="1000", hi="100000")
        assert policy_applies(spec, "expense", Decimal("1000")) is True
        assert policy_applies(spec, "expense", Decimal("100000")) is True


class TestSelectPolicies:
    def test_sorted_by_step_order(self):
        specs = [
            _spec("b", step=2, role="director"),
            _spec("a", step=1, role="manager"),
        ]
        selected = select_policies(specs, "expense", Decimal("5000"))
        assert [s.policy_id for s in selected] == ["a", "b"]

    def test_filters_non_applicable(self):
        specs = [
            _spec("a", step=1, lo="0", hi="10000"),
            _spec("b", step=2, lo="100000"),  # not applicable for 5000
        ]
        selected = select_policies(specs, "expense", Decimal("5000"))
        assert [s.policy_id for s in selected] == ["a"]


class TestRequiredApprovalSteps:
    def test_ordered_roles(self):
        specs = [
            _spec("a", step=1, role="manager", lo="0"),
            _spec("b", step=2, role="director", lo="100000"),
        ]
        # 大口取引: 両ステップが必要
        assert required_approval_steps(specs, "expense", Decimal("200000")) == ["manager", "director"]

    def test_small_amount_single_step(self):
        specs = [
            _spec("a", step=1, role="manager", lo="0"),
            _spec("b", step=2, role="director", lo="100000"),
        ]
        assert required_approval_steps(specs, "expense", Decimal("5000")) == ["manager"]

    def test_duplicate_step_order_collapsed(self):
        specs = [
            _spec("a", step=1, role="manager"),
            _spec("b", step=1, role="manager2"),
        ]
        assert required_approval_steps(specs, "expense", Decimal("5000")) == ["manager"]

    def test_no_applicable_policy_empty(self):
        specs = [_spec("a", doc="invoice")]
        assert required_approval_steps(specs, "expense", Decimal("5000")) == []
