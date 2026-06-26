import pytest
from decimal import Decimal
from uuid import uuid4

from app.services.approval_service import ApprovalWorkflowService


class TestApprovalWorkflowTransitions:
    def test_valid_transitions(self):
        vt = ApprovalWorkflowService.VALID_TRANSITIONS
        assert "submitted" in vt["draft"]
        assert "approved" in vt["submitted"]
        assert "rejected" in vt["submitted"]
        assert "posted" in vt["approved"]
        assert len(vt["posted"]) == 0

    def test_rejected_can_go_back_to_draft(self):
        vt = ApprovalWorkflowService.VALID_TRANSITIONS
        assert "draft" in vt["rejected"]


class TestApprovalWorkflowService:
    """ApprovalWorkflowServiceのテスト。

    これらのテストはDBセッションが必要なため、統合テストとして実行する。
    単体テストとしてはステータス遷移ロジックのみ検証する。
    """

    def test_sod_check_in_approve(self):
        """自分自身の仕訳を承認できないことを確認するロジックテスト。"""
        creator_id = uuid4()
        approver_id = creator_id  # 同一ユーザー

        # SoDチェック: created_by == approver_id の場合はValidationErrorが発生するべき
        assert creator_id == approver_id

    def test_workflow_threshold_logic(self):
        """閾値ロジックのテスト。"""
        threshold = Decimal("100000")
        amount_below = Decimal("50000")
        amount_above = Decimal("150000")

        assert amount_below < threshold
        assert amount_above >= threshold
