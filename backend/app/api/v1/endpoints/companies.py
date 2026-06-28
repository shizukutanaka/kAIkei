from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.models.models import Company

router = APIRouter()


class CompanyResponse(BaseModel):
    company_id: str
    company_name: str
    company_code: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[CompanyResponse])
async def list_companies(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CompanyResponse]:
    """テナント内の会社一覧を取得する。"""
    result = await db.execute(
        select(Company).where(
            Company.tenant_id == current_user.tenant_id,
            Company.is_deleted == False,  # noqa: E712
            Company.is_active == True,  # noqa: E712
        ).order_by(Company.company_name)
    )
    companies = result.scalars().all()
    return [
        CompanyResponse(
            company_id=str(c.company_id),
            company_name=c.company_name,
            company_code=c.company_code,
            is_active=c.is_active,
        )
        for c in companies
    ]
