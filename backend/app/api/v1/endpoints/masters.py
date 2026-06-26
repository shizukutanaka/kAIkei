from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Account, SubAccount, TaxRule
from app.schemas.schemas import (
    AccountCreate,
    AccountResponse,
    AccountUpdate,
    SubAccountCreate,
    SubAccountResponse,
    TaxRuleCreate,
    TaxRuleResponse,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Account CRUD
# ---------------------------------------------------------------------------

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


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: UUID,
    payload: AccountUpdate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> Account:
    result = await db.execute(
        select(Account).where(Account.account_id == account_id, Account.is_deleted == False)  # noqa: E712
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if payload.account_name is not None:
        account.account_name = payload.account_name
    if payload.account_type is not None:
        account.account_type = payload.account_type
    if payload.is_active is not None:
        account.is_active = payload.is_active

    await db.flush()
    await db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Account).where(Account.account_id == account_id, Account.is_deleted == False)  # noqa: E712
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account.is_deleted = True
    account.is_active = False
    await db.flush()


# ---------------------------------------------------------------------------
# SubAccount CRUD
# ---------------------------------------------------------------------------

@router.post("/sub-accounts", response_model=SubAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_sub_account(
    payload: SubAccountCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> SubAccount:
    account_result = await db.execute(
        select(Account).where(Account.account_id == payload.account_id, Account.is_deleted == False)  # noqa: E712
    )
    if not account_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Parent account not found")

    existing = await db.execute(
        select(SubAccount).where(
            SubAccount.account_id == payload.account_id,
            SubAccount.sub_account_code == payload.sub_account_code,
            SubAccount.is_deleted == False,  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Sub-account code already exists")

    sub = SubAccount(
        account_id=payload.account_id,
        sub_account_code=payload.sub_account_code,
        sub_account_name=payload.sub_account_name,
    )
    db.add(sub)
    await db.flush()
    await db.refresh(sub)
    return sub


@router.get("/sub-accounts/by-account/{account_id}", response_model=list[SubAccountResponse])
async def list_sub_accounts(
    account_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[SubAccount]:
    result = await db.execute(
        select(SubAccount).where(
            SubAccount.account_id == account_id,
            SubAccount.is_deleted == False,  # noqa: E712
            SubAccount.is_active == True,  # noqa: E712
        ).order_by(SubAccount.sub_account_code)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# TaxRule CRUD
# ---------------------------------------------------------------------------

@router.post("/tax-rules", response_model=TaxRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_tax_rule(
    payload: TaxRuleCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> TaxRule:
    existing = await db.execute(
        select(TaxRule).where(
            TaxRule.company_id == payload.company_id,
            TaxRule.tax_code == payload.tax_code,
            TaxRule.is_deleted == False,  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Tax code already exists")

    rule = TaxRule(
        company_id=payload.company_id,
        tax_code=payload.tax_code,
        tax_name=payload.tax_name,
        tax_rate=payload.tax_rate,
        tax_type=payload.tax_type,
        is_inclusive=payload.is_inclusive,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


@router.get("/tax-rules", response_model=list[TaxRuleResponse])
async def list_tax_rules(
    company_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[TaxRule]:
    result = await db.execute(
        select(TaxRule).where(
            TaxRule.company_id == company_id,
            TaxRule.is_deleted == False,  # noqa: E712
        ).order_by(TaxRule.tax_code)
    )
    return list(result.scalars().all())
