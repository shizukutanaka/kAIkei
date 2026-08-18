from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission, verified_company_id
from app.core.rbac import Permission
from app.schemas.schemas import (
    ApprovalPolicyCreate,
    ApprovalPolicyResponse,
    ApprovalStepsResponse,
)
from app.services import approval_policy

router = APIRouter()


@router.post("", response_model=ApprovalPolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: ApprovalPolicyCreate,
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> ApprovalPolicyResponse:
    """承認ポリシーを作成する。"""
    policy = await approval_policy.create_policy(
        db,
        tenant_id=current_user.tenant_id,
        company_id=company_id,
        document_type=payload.document_type,
        approver_role=payload.approver_role,
        step_order=payload.step_order,
        min_amount=payload.min_amount,
        max_amount=payload.max_amount,
    )
    return ApprovalPolicyResponse.model_validate(policy)


@router.get("", response_model=list[ApprovalPolicyResponse])
async def list_policies(
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    document_type: str | None = Query(None),
    active_only: bool = Query(False),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalPolicyResponse]:
    """承認ポリシーを一覧取得する。"""
    policies = await approval_policy.list_policies(
        db, company_id=company_id, document_type=document_type, active_only=active_only
    )
    return [ApprovalPolicyResponse.model_validate(p) for p in policies]


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: UUID,
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_DELETE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """承認ポリシーを削除する。"""
    deleted = await approval_policy.delete_policy(db, company_id=company_id, policy_id=policy_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Approval policy not found")


@router.get("/resolve", response_model=ApprovalStepsResponse)
async def resolve_steps(
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    document_type: str = Query(...),
    amount: Decimal = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> ApprovalStepsResponse:
    """対象文書・金額に必要な承認ステップ（承認ロール列）を解決する。"""
    steps = await approval_policy.resolve_required_steps(
        db, company_id=company_id, document_type=document_type, amount=amount
    )
    return ApprovalStepsResponse(document_type=document_type, amount=amount, required_steps=steps)
