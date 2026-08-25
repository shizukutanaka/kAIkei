from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rbac import Permission
from app.models.models import Company

router = APIRouter()

# 消費税の課税方式（一般課税／簡易課税）。
VALID_TAX_METHODS = {"general", "simplified"}


class CompanyResponse(BaseModel):
    company_id: str
    company_name: str
    company_code: str
    is_active: bool

    model_config = {"from_attributes": True}


class CompanyCreate(BaseModel):
    """会社の新規作成。

    `tenant_id` は受け取らない。作成者のテナントに固定することで、
    他テナントに会社を作られる余地を無くす。
    """

    company_name: str = Field(min_length=1, max_length=200)
    company_code: str = Field(min_length=1, max_length=50)
    legal_name: str | None = Field(default=None, max_length=300)
    fiscal_year_start_month: int = Field(default=4, ge=1, le=12)
    tax_method: str = Field(default="general")
    # 協会けんぽの料率は都道府県・年度で変わる。未設定なら代表値を使う。
    health_insurance_rate: Decimal | None = Field(default=None, ge=0, le=1)
    care_insurance_rate: Decimal | None = Field(default=None, ge=0, le=1)


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


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> CompanyResponse:
    """会社を作成する。

    このエンドポイントが無いと、登録直後の利用者はどの画面も使えない
    （ほぼ全ての機能が company_id を要求するため）。

    テナントは**認証情報から取る**。クライアントから受け取ると、他テナントに
    会社を作れてしまい、テナント分離が根元から崩れる。
    """
    if payload.tax_method not in VALID_TAX_METHODS:
        raise HTTPException(
            status_code=422,
            detail=f"無効な課税方式: {payload.tax_method}。有効な値: {', '.join(sorted(VALID_TAX_METHODS))}",
        )

    duplicate = await db.execute(
        select(Company).where(
            Company.tenant_id == current_user.tenant_id,
            Company.company_code == payload.company_code,
            Company.is_deleted == False,  # noqa: E712
        )
    )
    if duplicate.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="会社コードが既に使われています")

    company = Company(
        tenant_id=current_user.tenant_id,
        company_name=payload.company_name,
        company_code=payload.company_code,
        legal_name=payload.legal_name,
        fiscal_year_start_month=payload.fiscal_year_start_month,
        tax_method=payload.tax_method,
        health_insurance_rate=payload.health_insurance_rate,
        care_insurance_rate=payload.care_insurance_rate,
    )
    db.add(company)
    await db.flush()
    await db.refresh(company)
    return CompanyResponse(
        company_id=str(company.company_id),
        company_name=company.company_name,
        company_code=company.company_code,
        is_active=company.is_active,
    )
