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


class EmployeeCreate(BaseModel):
    company_id: UUID
    employee_code: str
    employee_name: str
    department: str | None = None
    position: str | None = None
    employment_type: str = "full_time"
    base_salary: Decimal = Field(default=Decimal("0"), ge=0)
    hourly_rate: Decimal = Field(default=Decimal("0"), ge=0)
    hire_date: date


class EmployeeResponse(BaseModel):
    employee_id: UUID
    company_id: UUID
    employee_code: str
    employee_name: str
    department: str | None
    position: str | None
    employment_type: str
    base_salary: Decimal
    hourly_rate: Decimal
    hire_date: date
    termination_date: date | None
    is_active: bool

    model_config = {"from_attributes": True}


class PayrollCalculateRequest(BaseModel):
    company_id: UUID
    payroll_year: int = Field(ge=2000, le=2100)
    payroll_month: int = Field(ge=1, le=12)
    overtime_hours: dict[UUID, Decimal] = Field(default_factory=dict)


class PayrollRecordResponse(BaseModel):
    payroll_id: UUID
    employee_id: UUID
    company_id: UUID
    payroll_year: int
    payroll_month: int
    base_salary: Decimal
    overtime_hours: Decimal
    overtime_pay: Decimal
    total_gross: Decimal
    income_tax: Decimal
    social_insurance: Decimal
    total_deductions: Decimal
    net_pay: Decimal
    status: str
    employee_name: str | None = None

    model_config = {"from_attributes": True}


class PartnerCreate(BaseModel):
    company_id: UUID
    partner_code: str
    partner_name: str
    partner_type: str = "customer"
    postal_code: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    contact_person: str | None = None
    payment_terms: str | None = None


class PartnerUpdate(BaseModel):
    partner_name: str | None = None
    partner_type: str | None = None
    postal_code: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    contact_person: str | None = None
    payment_terms: str | None = None
    is_active: bool | None = None


class PartnerResponse(BaseModel):
    partner_id: UUID
    company_id: UUID
    partner_code: str
    partner_name: str
    partner_type: str
    postal_code: str | None
    address: str | None
    phone: str | None
    email: str | None
    contact_person: str | None
    payment_terms: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class BonusCalculateRequest(BaseModel):
    company_id: UUID
    bonus_year: int = Field(ge=2000, le=2100)
    bonus_term: str = Field(description="summer, winter, etc.")
    bonus_base_months: Decimal = Field(default=Decimal("2.0"), ge=0)
    performance_factors: dict[UUID, Decimal] = Field(default_factory=dict)


class BonusRecordResponse(BaseModel):
    bonus_id: UUID
    employee_id: UUID
    company_id: UUID
    bonus_year: int
    bonus_term: str
    bonus_amount: Decimal
    bonus_base_months: Decimal
    performance_factor: Decimal
    income_tax: Decimal
    social_insurance: Decimal
    total_deductions: Decimal
    net_pay: Decimal
    status: str
    employee_name: str | None = None

    model_config = {"from_attributes": True}
