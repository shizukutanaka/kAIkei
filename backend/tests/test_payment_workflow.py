import pytest

from app.services.payment_workflow import next_payment_status


class TestNextPaymentStatus:
    def test_draft_to_approved(self):
        assert next_payment_status("draft", "approve") == "approved"

    def test_approved_to_executed(self):
        assert next_payment_status("approved", "execute") == "executed"

    def test_draft_and_approved_can_cancel(self):
        assert next_payment_status("draft", "cancel") == "cancelled"
        assert next_payment_status("approved", "cancel") == "cancelled"

    def test_cannot_execute_draft(self):
        with pytest.raises(ValueError):
            next_payment_status("draft", "execute")

    def test_cannot_approve_approved(self):
        with pytest.raises(ValueError):
            next_payment_status("approved", "approve")

    def test_cannot_transition_executed_or_cancelled(self):
        for st in ("executed", "cancelled"):
            for action in ("approve", "execute", "cancel"):
                with pytest.raises(ValueError):
                    next_payment_status(st, action)

    def test_unknown_action(self):
        with pytest.raises(ValueError):
            next_payment_status("draft", "delete")
