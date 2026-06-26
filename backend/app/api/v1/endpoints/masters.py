from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Account
from app.schemas.schemas import AccountCreate, AccountResponse

router = APIRouter()


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> Account:
    existing = await db.execute(
        select(Account).where(
            Account.company_id == payload.company_id,
            Account.account_code == payload.account_code,
            Account.is_deleted == False,  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Account code already exists")

    account = Account(
        company_id=payload.company_id,
        account_code=payload.account_code,
        account_name=payload.account_name,
        account_type=payload.account_type,
        debit_credit=payload.debit_credit,
        parent_account_id=payload.parent_account_id,
    )
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    company_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[Account]:
    result = await db.execute(
        select(Account).where(
            Account.company_id == company_id,
            Account.is_deleted == False,  # noqa: E712
            Account.is_active == True,  # noqa: E712
        ).order_by(Account.account_code)
    )
    return list(result.scalars().all())


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> Account:
    result = await db.execute(
        select(Account).where(Account.account_id == account_id, Account.is_deleted == False)  # noqa: E712
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account
