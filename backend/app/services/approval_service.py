import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role, has_permission, Permission
from app.models.models import (
    ApprovalLog,
    ApprovalWorkflow,
    JournalHeader,
    JournalLine,
    User,
)
from app.services.validation_engine import ValidationError

logger = logging.getLogger(__name__)


class ApprovalWorkflowService:
    """承認ワークフロー管理サービス。

    ステータス遷移:
    draft → submitted → approved → posted
                ↘ rejected
    """

    VALID_TRANSITIONS: dict[str, set[str]] = {
        "draft": {"submitted", "rejected"},
        "submitted": {"approved", "rejected", "draft"},
        "approved": {"posted", "draft"},
        "posted": set(),
        "rejected": {"draft"},
    }

    @staticmethod
    async def submit_for_approval(
        db: AsyncSession,
        journal_header_id: UUID,
        submitter_id: UUID,
    ) -> JournalHeader:
        """仕訳を承認待ちに提出する（draft → submitted）。"""
        journal = await ApprovalWorkflowService._get_journal(db, journal_header_id)

        if journal.approval_status != "draft":
            raise ValueError(f"Cannot submit journal in status: {journal.approval_status}")

        if journal.created_by != submitter_id:
            raise ValidationError(
                code="AUTH-001",
                message="Only the creator can submit the journal for approval",
            )

        total_amount = await ApprovalWorkflowService._get_journal_total(db, journal_header_id)

        workflow = await ApprovalWorkflowService._get_applicable_workflow(
            db, journal.company_id, total_amount
        )

        if workflow:
            journal.approval_status = "submitted"
        else:
            journal.approval_status = "submitted"

        await ApprovalWorkflowService._log_action(
            db, journal_header_id, "submit", "draft", "submitted", submitter_id
        )

        await db.flush()
        await db.refresh(journal)
        return journal

    @staticmethod
    async def approve(
        db: AsyncSession,
        journal_header_id: UUID,
        approver_id: UUID,
        comment: str | None = None,
    ) -> JournalHeader:
        """仕訳を承認する（submitted → approved）。"""
        journal = await ApprovalWorkflowService._get_journal(db, journal_header_id)

        if journal.approval_status != "submitted":
            raise ValueError(f"Cannot approve journal in status: {journal.approval_status}")

        if journal.created_by == approver_id:
            raise ValidationError(
                code="SOD-001",
                message="Segregation of Duties violation: creator cannot approve their own journal",
            )

        approver = await ApprovalWorkflowService._get_user(db, approver_id)
        if not has_permission(approver.role, Permission.JOURNAL_APPROVE):
            raise ValidationError(
                code="RBAC-001",
                message=f"Role '{approver.role}' does not have approval permission",
            )

        total_amount = await ApprovalWorkflowService._get_journal_total(db, journal_header_id)
        workflow = await ApprovalWorkflowService._get_applicable_workflow(
            db, journal.company_id, total_amount
        )

        if workflow:
            required_roles = [r.strip() for r in workflow.required_approver_roles.split(",")]
            if approver.role not in required_roles:
                raise ValidationError(
                    code="WF-001",
                    message=f"Workflow requires approver with role in: {required_roles}",
                )

        journal.approval_status = "approved"
        journal.approved_by = approver_id

        await ApprovalWorkflowService._log_action(
            db, journal_header_id, "approve", "submitted", "approved", approver_id, comment
        )

        await db.flush()
        await db.refresh(journal)
        return journal

    @staticmethod
    async def reject(
        db: AsyncSession,
        journal_header_id: UUID,
        rejecter_id: UUID,
        comment: str | None = None,
    ) -> JournalHeader:
        """仕訳を差し戻す（submitted → rejected）。"""
        journal = await ApprovalWorkflowService._get_journal(db, journal_header_id)

        if journal.approval_status not in ("submitted", "approved"):
            raise ValueError(f"Cannot reject journal in status: {journal.approval_status}")

        if journal.created_by == rejecter_id:
            raise ValidationError(
                code="SOD-001",
                message="Segregation of Duties violation: creator cannot reject their own journal",
            )

        from_status = journal.approval_status
        journal.approval_status = "rejected"
        journal.approved_by = None

        await ApprovalWorkflowService._log_action(
            db, journal_header_id, "reject", from_status, "rejected", rejecter_id, comment
        )

        await db.flush()
        await db.refresh(journal)
        return journal

    @staticmethod
    async def post(
        db: AsyncSession,
        journal_header_id: UUID,
        actor_id: UUID,
    ) -> JournalHeader:
        """承認済み仕訳を転記する（approved → posted）。"""
        journal = await ApprovalWorkflowService._get_journal(db, journal_header_id)

        if journal.approval_status != "approved":
            raise ValueError(f"Cannot post journal in status: {journal.approval_status}")

        actor = await ApprovalWorkflowService._get_user(db, actor_id)
        if not has_permission(actor.role, Permission.JOURNAL_POST):
            raise ValidationError(
                code="RBAC-001",
                message=f"Role '{actor.role}' does not have post permission",
            )

        journal.approval_status = "posted"

        await ApprovalWorkflowService._log_action(
            db, journal_header_id, "post", "approved", "posted", actor_id
        )

        from app.services.journal_service import JournalService
        await JournalService._update_monthly_balance(db, journal)

        await db.flush()
        await db.refresh(journal)
        return journal

    @staticmethod
    async def get_approval_history(
        db: AsyncSession,
        journal_header_id: UUID,
    ) -> list[ApprovalLog]:
        """承認履歴を取得する。"""
        result = await db.execute(
            select(ApprovalLog)
            .where(ApprovalLog.journal_header_id == journal_header_id)
            .order_by(ApprovalLog.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_workflow(
        db: AsyncSession,
        company_id: UUID,
        name: str,
        threshold_amount: Decimal,
        required_approver_roles: str = "approver,admin",
        description: str | None = None,
    ) -> ApprovalWorkflow:
        """承認ワークフロー定義を作成する。"""
        workflow = ApprovalWorkflow(
            company_id=company_id,
            name=name,
            description=description,
            trigger_type="amount_threshold",
            threshold_amount=threshold_amount,
            required_approver_roles=required_approver_roles,
        )
        db.add(workflow)
        await db.flush()
        await db.refresh(workflow)
        return workflow

    @staticmethod
    async def list_workflows(
        db: AsyncSession,
        company_id: UUID,
    ) -> list[ApprovalWorkflow]:
        """会社の承認ワークフロー一覧を取得する。"""
        result = await db.execute(
            select(ApprovalWorkflow).where(
                ApprovalWorkflow.company_id == company_id,
                ApprovalWorkflow.is_deleted == False,  # noqa: E712
                ApprovalWorkflow.is_active == True,  # noqa: E712
            ).order_by(ApprovalWorkflow.threshold_amount)
        )
        return list(result.scalars().all())

    @staticmethod
    async def _get_journal(db: AsyncSession, journal_header_id: UUID) -> JournalHeader:
        result = await db.execute(
            select(JournalHeader).where(
                JournalHeader.journal_header_id == journal_header_id,
                JournalHeader.is_deleted == False,  # noqa: E712
            )
        )
        journal = result.scalar_one_or_none()
        if not journal:
            raise ValueError("Journal not found")
        return journal

    @staticmethod
    async def _get_user(db: AsyncSession, user_id: UUID) -> User:
        result = await db.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")
        return user

    @staticmethod
    async def _get_journal_total(db: AsyncSession, journal_header_id: UUID) -> Decimal:
        result = await db.execute(
            select(JournalLine).where(
                JournalLine.journal_header_id == journal_header_id,
                JournalLine.is_deleted == False,  # noqa: E712
                JournalLine.debit_credit == "debit",
            )
        )
        lines = result.scalars().all()
        return sum((line.amount for line in lines), Decimal("0"))

    @staticmethod
    async def _get_applicable_workflow(
        db: AsyncSession,
        company_id: UUID,
        amount: Decimal,
    ) -> ApprovalWorkflow | None:
        result = await db.execute(
            select(ApprovalWorkflow).where(
                ApprovalWorkflow.company_id == company_id,
                ApprovalWorkflow.is_active == True,  # noqa: E712
                ApprovalWorkflow.is_deleted == False,  # noqa: E712
                ApprovalWorkflow.threshold_amount <= amount,
            ).order_by(ApprovalWorkflow.threshold_amount.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _log_action(
        db: AsyncSession,
        journal_header_id: UUID,
        action: str,
        from_status: str,
        to_status: str,
        actor_id: UUID,
        comment: str | None = None,
    ) -> None:
        log = ApprovalLog(
            journal_header_id=journal_header_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            comment=comment,
        )
        db.add(log)
