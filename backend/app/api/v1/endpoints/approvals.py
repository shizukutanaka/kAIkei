from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rbac import Permission
from app.models.models import ApprovalLog, ApprovalWorkflow
from app.services.approval_service import ApprovalWorkflowService
from app.services.validation_engine import ValidationError
from app.services.notification_service import create_notification
from app.schemas.schemas import NotificationCreate

router = APIRouter()


class SubmitRequest(BaseModel):
    journal_header_id: UUID


class ApproveRequest(BaseModel):
    journal_header_id: UUID
    comment: str | None = None


class RejectRequest(BaseModel):
    journal_header_id: UUID
    comment: str | None = None


class PostRequest(BaseModel):
    journal_header_id: UUID


class WorkflowCreateRequest(BaseModel):
    company_id: UUID
    name: str
    threshold_amount: float
    required_approver_roles: str = "approver,admin"
    description: str | None = None


class ApprovalLogResponse(BaseModel):
    log_id: UUID
    journal_header_id: UUID
    action: str
    from_status: str
    to_status: str
    actor_id: UUID
    comment: str | None
    created_at: str

    model_config = {"from_attributes": True}


class WorkflowResponse(BaseModel):
    workflow_id: UUID
    company_id: UUID
    name: str
    description: str | None
    trigger_type: str
    threshold_amount: float
    required_approver_roles: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.post("/submit", dependencies=[Depends(require_permission(Permission.JOURNAL_CREATE))])
async def submit_for_approval(
    payload: SubmitRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """仕訳を承認待ちに提出する（draft → submitted）。"""
    try:
        journal = await ApprovalWorkflowService.submit_for_approval(
            db, payload.journal_header_id, current_user.user_id
        )
        try:
            await create_notification(db, current_user.tenant_id, NotificationCreate(
                company_id=journal.company_id,
                user_id=journal.created_by,
                category="approval",
                priority="normal",
                title=f"仕訳 {journal.journal_number} が提出されました",
                body=f"承認待ちの仕訳があります: {journal.summary or ''}",
                action_url=f"/approvals",
            ))
        except Exception:
            pass
        return {
            "journal_header_id": str(journal.journal_header_id),
            "approval_status": journal.approval_status,
            "message": "Journal submitted for approval",
        }
    except ValidationError as e:
        raise HTTPException(status_code=403, detail={"code": e.code, "message": e.message})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/approve", dependencies=[Depends(require_permission(Permission.JOURNAL_APPROVE))])
async def approve_journal(
    payload: ApproveRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """仕訳を承認する（submitted → approved）。"""
    try:
        journal = await ApprovalWorkflowService.approve(
            db, payload.journal_header_id, current_user.user_id, payload.comment
        )
        try:
            await create_notification(db, current_user.tenant_id, NotificationCreate(
                company_id=journal.company_id,
                user_id=journal.created_by,
                category="approval",
                priority="normal",
                title=f"仕訳 {journal.journal_number} が承認されました",
                body=f"承認されました: {journal.summary or ''}",
                action_url=f"/journals/{journal.journal_header_id}",
            ))
        except Exception:
            pass
        return {
            "journal_header_id": str(journal.journal_header_id),
            "approval_status": journal.approval_status,
            "approved_by": str(journal.approved_by) if journal.approved_by else None,
            "message": "Journal approved",
        }
    except ValidationError as e:
        raise HTTPException(status_code=403, detail={"code": e.code, "message": e.message})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reject", dependencies=[Depends(require_permission(Permission.JOURNAL_APPROVE))])
async def reject_journal(
    payload: RejectRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """仕訳を差し戻す（submitted → rejected）。"""
    try:
        journal = await ApprovalWorkflowService.reject(
            db, payload.journal_header_id, current_user.user_id, payload.comment
        )
        try:
            await create_notification(db, current_user.tenant_id, NotificationCreate(
                company_id=journal.company_id,
                user_id=journal.created_by,
                category="approval",
                priority="high",
                title=f"仕訳 {journal.journal_number} が差し戻されました",
                body=f"差し戻し理由: {payload.comment or 'コメントなし'}",
                action_url=f"/journals/{journal.journal_header_id}",
            ))
        except Exception:
            pass
        return {
            "journal_header_id": str(journal.journal_header_id),
            "approval_status": journal.approval_status,
            "message": "Journal rejected",
        }
    except ValidationError as e:
        raise HTTPException(status_code=403, detail={"code": e.code, "message": e.message})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/post", dependencies=[Depends(require_permission(Permission.JOURNAL_POST))])
async def post_journal(
    payload: PostRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """承認済み仕訳を転記する（approved → posted）。"""
    try:
        journal = await ApprovalWorkflowService.post(
            db, payload.journal_header_id, current_user.user_id
        )
        try:
            await create_notification(db, current_user.tenant_id, NotificationCreate(
                company_id=journal.company_id,
                user_id=journal.created_by,
                category="journal",
                priority="normal",
                title=f"仕訳 {journal.journal_number} が転記されました",
                body=f"転記完了: {journal.summary or ''}",
                action_url=f"/journals/{journal.journal_header_id}",
            ))
        except Exception:
            pass
        return {
            "journal_header_id": str(journal.journal_header_id),
            "approval_status": journal.approval_status,
            "message": "Journal posted",
        }
    except ValidationError as e:
        raise HTTPException(status_code=403, detail={"code": e.code, "message": e.message})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/history/{journal_header_id}")
async def get_approval_history(
    journal_header_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalLogResponse]:
    """承認履歴を取得する。"""
    logs = await ApprovalWorkflowService.get_approval_history(db, journal_header_id)
    return [
        ApprovalLogResponse(
            log_id=log.log_id,
            journal_header_id=log.journal_header_id,
            action=log.action,
            from_status=log.from_status,
            to_status=log.to_status,
            actor_id=log.actor_id,
            comment=log.comment,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]


@router.post("/workflows", dependencies=[Depends(require_permission(Permission.USER_MANAGE))])
async def create_workflow(
    payload: WorkflowCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowResponse:
    """承認ワークフロー定義を作成する。"""
    from decimal import Decimal

    workflow = await ApprovalWorkflowService.create_workflow(
        db,
        company_id=payload.company_id,
        name=payload.name,
        threshold_amount=Decimal(str(payload.threshold_amount)),
        required_approver_roles=payload.required_approver_roles,
        description=payload.description,
    )
    return WorkflowResponse.model_validate(workflow)


@router.get("/workflows")
async def list_workflows(
    company_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowResponse]:
    """会社の承認ワークフロー一覧を取得する。"""
    workflows = await ApprovalWorkflowService.list_workflows(db, company_id)
    return [WorkflowResponse.model_validate(w) for w in workflows]
