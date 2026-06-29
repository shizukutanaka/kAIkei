from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
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
# Standard Chart of Accounts (日本標準勘定科目セット)
# Based on SKR (Standard Kontenrahmen) adapted for Japanese GAAP
# ---------------------------------------------------------------------------

STANDARD_CHART_OF_ACCOUNTS = [
    # (code, name, type, debit_credit)
    # --- Assets (資産) ---
    ("1000", "現金", "asset", "debit"),
    ("1010", "当座預金", "asset", "debit"),
    ("1020", "普通預金", "asset", "debit"),
    ("1030", "定期預金", "asset", "debit"),
    ("1100", "売掛金", "asset", "debit"),
    ("1110", "受取手形", "asset", "debit"),
    ("1120", "電子記録債権", "asset", "debit"),
    ("1150", "前払金", "asset", "debit"),
    ("1160", "未収入金", "asset", "debit"),
    ("1200", "仮払消費税", "asset", "debit"),
    ("1210", "前払費用", "asset", "debit"),
    ("1300", "商品", "asset", "debit"),
    ("1310", "原材料", "asset", "debit"),
    ("1320", "仕掛品", "asset", "debit"),
    ("1330", "半製品", "asset", "debit"),
    ("1340", "製品", "asset", "debit"),
    ("1400", "消耗品費", "asset", "debit"),
    ("1500", "前渡金", "asset", "debit"),
    ("1600", "ソフトウェア", "asset", "debit"),
    ("1610", "リース資産", "asset", "debit"),
    ("1700", "建物", "asset", "debit"),
    ("1710", "建物附属設備", "asset", "debit"),
    ("1720", "構築物", "asset", "debit"),
    ("1730", "機械装置", "asset", "debit"),
    ("1740", "車両運搬具", "asset", "debit"),
    ("1750", "工具器具備品", "asset", "debit"),
    ("1760", "土地", "asset", "debit"),
    ("1770", "減価償却累計額", "asset", "credit"),
    ("1800", "のれん", "asset", "debit"),
    ("1900", "長期前払費用", "asset", "debit"),
    # --- Liabilities (負債) ---
    ("2000", "買掛金", "liability", "credit"),
    ("2010", "支払手形", "liability", "credit"),
    ("2020", "電子記録債務", "liability", "credit"),
    ("2050", "未払金", "liability", "credit"),
    ("2060", "未払費用", "liability", "credit"),
    ("2070", "前受金", "liability", "credit"),
    ("2080", "預り金", "liability", "credit"),
    ("2100", "仮受消費税", "liability", "credit"),
    ("2110", "未払消費税", "liability", "credit"),
    ("2120", "未払法人税等", "liability", "credit"),
    ("2130", "未払所得税", "liability", "credit"),
    ("2140", "法定福利費預り金", "liability", "credit"),
    ("2200", "短期借入金", "liability", "credit"),
    ("2210", "リース債務", "liability", "credit"),
    ("2300", "長期借入金", "liability", "credit"),
    ("2400", "社債", "liability", "credit"),
    ("2500", "引当金", "liability", "credit"),
    # --- Equity (純資産) ---
    ("3000", "資本金", "equity", "credit"),
    ("3100", "資本準備金", "equity", "credit"),
    ("3200", "利益準備金", "equity", "credit"),
    ("3300", "その他資本剰余金", "equity", "credit"),
    ("3400", "繰越利益剰余金", "equity", "credit"),
    ("3500", "任意積立金", "equity", "credit"),
    ("3900", "当期純利益", "equity", "credit"),
    # --- Revenue (収益) ---
    ("4000", "売上", "revenue", "credit"),
    ("4010", "売上値引・戻り", "revenue", "debit"),
    ("4100", "受取手形売却損", "revenue", "debit"),
    ("4200", "受取利息", "revenue", "credit"),
    ("4300", "受取配当金", "revenue", "credit"),
    ("4400", "有価証券売却益", "revenue", "credit"),
    ("4500", "固定資産売却益", "revenue", "credit"),
    ("4600", "営業外収益", "revenue", "credit"),
    ("4900", "雑収入", "revenue", "credit"),
    # --- Expenses (費用) ---
    ("5000", "売上原価", "expense", "debit"),
    ("5100", "給与手当", "expense", "debit"),
    ("5110", "賞与", "expense", "debit"),
    ("5120", "退職金", "expense", "debit"),
    ("5130", "法定福利費", "expense", "debit"),
    ("5140", "福利厚生費", "expense", "debit"),
    ("5200", "旅費交通費", "expense", "debit"),
    ("5210", "接待交際費", "expense", "debit"),
    ("5220", "会議費", "expense", "debit"),
    ("5230", "広告宣伝費", "expense", "debit"),
    ("5240", "発送費", "expense", "debit"),
    ("5250", "消耗品費", "expense", "debit"),
    ("5260", "通信費", "expense", "debit"),
    ("5270", "水道光熱費", "expense", "debit"),
    ("5280", "減価償却費", "expense", "debit"),
    ("5290", "租税公課", "expense", "debit"),
    ("5300", "地代家賃", "expense", "debit"),
    ("5310", "保険料", "expense", "debit"),
    ("5320", "修繕費", "expense", "debit"),
    ("5330", "雑費", "expense", "debit"),
    ("5400", "支払利息", "expense", "debit"),
    ("5410", "手形売却損", "expense", "debit"),
    ("5420", "貸倒損失", "expense", "debit"),
    ("5430", "固定資産売却損", "expense", "debit"),
    ("5440", "有価証券売却損", "expense", "debit"),
    ("5900", "法人税等", "expense", "debit"),
]


@router.post("/initialize-standard-accounts", response_model=list[AccountResponse])
async def initialize_standard_accounts(
    company_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> list[Account]:
    """日本標準勘定科目セットを初期化する。

    既存の勘定科目がある場合は重複をスキップし、不足分のみ追加する。
    市販会計ソフト（Freee/MoneyForward/Yayoi等）と互換性のある標準科目体系。
    """
    # Check existing accounts
    existing_result = await db.execute(
        select(Account.account_code).where(
            Account.company_id == company_id,
            Account.is_deleted == False,  # noqa: E712
        )
    )
    existing_codes = {row[0] for row in existing_result.all()}

    created: list[Account] = []
    for code, name, acct_type, dc in STANDARD_CHART_OF_ACCOUNTS:
        if code in existing_codes:
            continue
        account = Account(
            company_id=company_id,
            account_code=code,
            account_name=name,
            account_type=acct_type,
            debit_credit=dc,
        )
        db.add(account)
        created.append(account)

    if created:
        await db.flush()
        for acct in created:
            await db.refresh(acct)

    return created


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
