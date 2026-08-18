from contextlib import suppress
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission, verified_company_id
from app.core.rbac import Permission
from app.core.tenant_scope import scope_to_tenant
from app.models.models import DepreciationRecord, FixedAsset
from app.schemas.schemas import FixedAssetCreate, FixedAssetResponse
from app.services.auto_journal import generate_depreciation_journal
from app.services.depreciation import DepreciationService

router = APIRouter()


def _to_response(asset: FixedAsset) -> FixedAssetResponse:
    return FixedAssetResponse(
        asset_id=asset.asset_id,
        company_id=asset.company_id,
        asset_code=asset.asset_code,
        asset_name=asset.asset_name,
        asset_category=asset.asset_category,
        acquisition_date=asset.acquisition_date,
        acquisition_cost=asset.acquisition_cost,
        useful_life_months=asset.useful_life_months,
        depreciation_method=asset.depreciation_method,
        salvage_value=asset.salvage_value,
        accumulated_depreciation=asset.accumulated_depreciation,
        is_disposed=asset.is_disposed,
        disposal_date=asset.disposal_date,
        net_book_value=asset.acquisition_cost - asset.accumulated_depreciation,
    )


@router.post("", response_model=FixedAssetResponse, status_code=status.HTTP_201_CREATED)
async def create_fixed_asset(
    payload: FixedAssetCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> FixedAssetResponse:
    existing = await db.execute(
        select(FixedAsset).where(
            FixedAsset.company_id == payload.company_id,
            FixedAsset.asset_code == payload.asset_code,
            FixedAsset.is_deleted == False,  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Asset code already exists")

    asset = FixedAsset(
        company_id=payload.company_id,
        asset_code=payload.asset_code,
        asset_name=payload.asset_name,
        asset_category=payload.asset_category,
        acquisition_date=payload.acquisition_date,
        acquisition_cost=payload.acquisition_cost,
        useful_life_months=payload.useful_life_months,
        depreciation_method=payload.depreciation_method,
        salvage_value=payload.salvage_value,
        account_id=payload.account_id,
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return _to_response(asset)


@router.get("", response_model=list[FixedAssetResponse])
async def list_fixed_assets(
    company_id: Annotated[UUID, Depends(verified_company_id)],
    category: str | None = Query(None, description="資産カテゴリで絞り込み"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[FixedAssetResponse]:
    stmt = select(FixedAsset).where(
        FixedAsset.company_id == company_id,
        FixedAsset.is_deleted == False,  # noqa: E712
    )
    if category:
        stmt = stmt.where(FixedAsset.asset_category == category)
    stmt = stmt.order_by(FixedAsset.asset_code)
    result = await db.execute(stmt)
    return [_to_response(a) for a in result.scalars().all()]


@router.get("/{asset_id}", response_model=FixedAssetResponse)
async def get_fixed_asset(
    asset_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> FixedAssetResponse:
    result = await db.execute(
        scope_to_tenant(
            select(FixedAsset).where(
                FixedAsset.asset_id == asset_id,
                FixedAsset.is_deleted == False,  # noqa: E712
            ),
            FixedAsset,
            current_user.tenant_id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Fixed asset not found")
    return _to_response(asset)


@router.get("/{asset_id}/schedule")
async def get_depreciation_schedule(
    asset_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[dict[str, Decimal | int]]:
    result = await db.execute(
        scope_to_tenant(
            select(FixedAsset).where(
                FixedAsset.asset_id == asset_id,
                FixedAsset.is_deleted == False,  # noqa: E712
            ),
            FixedAsset,
            current_user.tenant_id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Fixed asset not found")
    if asset.depreciation_method != "straight_line":
        raise HTTPException(status_code=400, detail=f"Unsupported depreciation method: {asset.depreciation_method}")

    schedule = DepreciationService.straight_line_schedule(
        acquisition_cost=asset.acquisition_cost,
        salvage_value=asset.salvage_value,
        useful_life_months=asset.useful_life_months,
        accumulated_depreciation=asset.accumulated_depreciation,
    )
    return [
        {
            "period_index": entry.period_index,
            "depreciation": entry.depreciation,
            "accumulated": entry.accumulated,
            "book_value": entry.book_value,
        }
        for entry in schedule
    ]


@router.post("/{asset_id}/depreciate", response_model=FixedAssetResponse)
async def run_depreciation(
    asset_id: UUID,
    fiscal_year: int = Query(..., description="償却年度"),  # noqa: B008
    month: int = Query(..., ge=1, le=12, description="償却月"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> FixedAssetResponse:
    result = await db.execute(
        scope_to_tenant(
            select(FixedAsset).where(
                FixedAsset.asset_id == asset_id,
                FixedAsset.is_deleted == False,  # noqa: E712
            ),
            FixedAsset,
            current_user.tenant_id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Fixed asset not found")
    if asset.is_disposed:
        raise HTTPException(status_code=400, detail="Asset is already disposed")

    if asset.depreciation_method == "straight_line":
        monthly_depreciation = DepreciationService.period_amount(
            acquisition_cost=asset.acquisition_cost,
            salvage_value=asset.salvage_value,
            useful_life_months=asset.useful_life_months,
            accumulated_depreciation=asset.accumulated_depreciation,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported depreciation method: {asset.depreciation_method}")

    new_accumulated = asset.accumulated_depreciation + monthly_depreciation
    depreciable_base = asset.acquisition_cost - asset.salvage_value
    if new_accumulated > depreciable_base:
        monthly_depreciation = depreciable_base - asset.accumulated_depreciation
        new_accumulated = depreciable_base

    asset.accumulated_depreciation = new_accumulated
    await db.flush()

    # Create depreciation record
    dep_record = DepreciationRecord(
        asset_id=asset.asset_id,
        fiscal_year=fiscal_year,
        month=month,
        depreciation_amount=monthly_depreciation,
        accumulated_amount=new_accumulated,
    )
    db.add(dep_record)

    # Auto-generate depreciation journal
    with suppress(ValueError):
        await generate_depreciation_journal(
            db,
            company_id=asset.company_id,
            asset_name=asset.asset_name,
            asset_code=asset.asset_code,
            fiscal_year=fiscal_year,
            month=month,
            depreciation_amount=monthly_depreciation,
            created_by=current_user.user_id,
        )

    await db.flush()
    await db.refresh(asset)
    return _to_response(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def dispose_fixed_asset(
    asset_id: UUID,
    disposal_date: date = Query(..., description="除却日"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> None:
    result = await db.execute(
        scope_to_tenant(
            select(FixedAsset).where(
                FixedAsset.asset_id == asset_id,
                FixedAsset.is_deleted == False,  # noqa: E712
            ),
            FixedAsset,
            current_user.tenant_id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Fixed asset not found")

    asset.is_disposed = True
    asset.disposal_date = disposal_date
    await db.flush()
