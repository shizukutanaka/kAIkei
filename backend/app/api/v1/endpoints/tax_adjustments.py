from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.schemas.schemas import (
    TaxAdjustmentComputeRequest,
    TaxAdjustmentComputeResponse,
    TaxAdjustmentRuleCreate,
    TaxAdjustmentRuleResponse,
)
from app.services import tax_adjustment

router = APIRouter()


@router.post("/rules", response_model=TaxAdjustmentRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: TaxAdjustmentRuleCreate,
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> TaxAdjustmentRuleResponse:
    """税務調整ルールを作成する。"""
    rule = await tax_adjustment.create_rule(
        db,
        tenant_id=current_user.tenant_id,
        company_id=company_id,
        name=payload.name,
        adjustment_type=payload.adjustment_type,
        calculation_method=payload.calculation_method,
        rate=payload.rate,
        limit_amount=payload.limit_amount,
        fixed_amount=payload.fixed_amount,
        target_account_code=payload.target_account_code,
    )
    return TaxAdjustmentRuleResponse.model_validate(rule)


@router.get("/rules", response_model=list[TaxAdjustmentRuleResponse])
async def list_rules(
    company_id: UUID = Query(...),
    active_only: bool = Query(False),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[TaxAdjustmentRuleResponse]:
    """税務調整ルールを一覧取得する。"""
    rules = await tax_adjustment.list_rules(db, company_id=company_id, active_only=active_only)
    return [TaxAdjustmentRuleResponse.model_validate(r) for r in rules]


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID,
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_DELETE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """税務調整ルールを削除する。"""
    deleted = await tax_adjustment.delete_rule(db, company_id=company_id, rule_id=rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tax adjustment rule not found")


@router.post("/compute", response_model=TaxAdjustmentComputeResponse)
async def compute(
    payload: TaxAdjustmentComputeRequest,
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> TaxAdjustmentComputeResponse:
    """有効な調整ルールを適用して課税所得を計算する。"""
    result = await tax_adjustment.compute_company_taxable_income(
        db,
        company_id=company_id,
        accounting_income=payload.accounting_income,
        base_amounts=payload.base_amounts,
    )
    return TaxAdjustmentComputeResponse(**result)
