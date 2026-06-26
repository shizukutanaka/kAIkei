from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str
    tenant_code: str


class UserResponse(BaseModel):
    user_id: UUID
    email: str
    display_name: str
    role: str
    tenant_id: UUID

    model_config = {"from_attributes": True}


class AccountCreate(BaseModel):
    company_id: UUID
    account_code: str
    account_name: str
    account_type: str
    debit_credit: str
    parent_account_id: UUID | None = None


class AccountUpdate(BaseModel):
    account_name: str | None = None
    account_type: str | None = None
    is_active: bool | None = None


class AccountResponse(BaseModel):
    account_id: UUID
    company_id: UUID
    account_code: str
    account_name: str
    account_type: str
    debit_credit: str
    is_active: bool

    model_config = {"from_attributes": True}


class SubAccountCreate(BaseModel):
    account_id: UUID
    sub_account_code: str
    sub_account_name: str


class SubAccountResponse(BaseModel):
    sub_account_id: UUID
    account_id: UUID
    sub_account_code: str
    sub_account_name: str
    is_active: bool

    model_config = {"from_attributes": True}


class TaxRuleCreate(BaseModel):
    company_id: UUID
    tax_code: str
    tax_name: str
    tax_rate: Decimal
    tax_type: str = "consumption"
    is_inclusive: bool = False


class TaxRuleResponse(BaseModel):
    tax_rule_id: UUID
    company_id: UUID
    tax_code: str
    tax_name: str
    tax_rate: Decimal
    tax_type: str
    is_inclusive: bool

    model_config = {"from_attributes": True}


class JournalLineCreate(BaseModel):
    debit_credit: str = Field(pattern="^(debit|credit)$")
    account_id: UUID
    sub_account_id: UUID | None = None
    department_id: UUID | None = None
    tax_rule_id: UUID | None = None
    amount: Decimal = Field(gt=0)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)
    description: str | None = None


class JournalCreate(BaseModel):
    company_id: UUID
    transaction_date: date
    voucher_type: str = Field(default="transfer", pattern="^(transfer|receipt|payment)$")
    summary: str | None = None
    lines: list[JournalLineCreate] = Field(min_length=2)


class JournalLineResponse(BaseModel):
    journal_line_id: UUID
    line_number: int
    debit_credit: str
    account_id: UUID
    sub_account_id: UUID | None
    amount: Decimal
    tax_amount: Decimal
    description: str | None

    model_config = {"from_attributes": True}


class JournalResponse(BaseModel):
    journal_header_id: UUID
    company_id: UUID
    journal_number: str
    transaction_date: date
    voucher_type: str
    summary: str | None
    approval_status: str
    is_voided: bool
    created_at: datetime
    lines: list[JournalLineResponse]

    model_config = {"from_attributes": True}


class JournalListResponse(BaseModel):
    items: list[JournalResponse]
    total: int
    page: int
    page_size: int


class FixedAssetCreate(BaseModel):
    company_id: UUID
    asset_code: str
    asset_name: str
    asset_category: str
    acquisition_date: date
    acquisition_cost: Decimal = Field(gt=0)
    useful_life_months: int = Field(gt=0)
    depreciation_method: str = "straight_line"
    salvage_value: Decimal = Field(default=Decimal("0"), ge=0)
    account_id: UUID | None = None


class FixedAssetResponse(BaseModel):
    asset_id: UUID
    company_id: UUID
    asset_code: str
    asset_name: str
    asset_category: str
    acquisition_date: date
    acquisition_cost: Decimal
    useful_life_months: int
    depreciation_method: str
    salvage_value: Decimal
    accumulated_depreciation: Decimal
    is_disposed: bool
    disposal_date: date | None
    net_book_value: Decimal

    model_config = {"from_attributes": True}
