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
    amount: Decimal
    tax_amount: Decimal = Decimal("0")
    description: str | None = None


class JournalCreate(BaseModel):
    company_id: UUID
    transaction_date: date
    voucher_type: str = Field(default="transfer", pattern="^(transfer|receipt|payment)$")
    summary: str | None = None
    lines: list[JournalLineCreate]


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


class YearEndAdjustmentRequest(BaseModel):
    company_id: UUID
    adjustment_year: int = Field(ge=2000, le=2100)
    dependents_override: dict[UUID, int] = Field(default_factory=dict)


class YearEndAdjustmentResponse(BaseModel):
    adjustment_id: UUID
    employee_id: UUID
    company_id: UUID
    adjustment_year: int
    annual_salary: Decimal
    annual_bonus: Decimal
    total_gross: Decimal
    withholding_tax_total: Decimal
    estimated_annual_tax: Decimal
    social_insurance_total: Decimal
    dependents: int
    dependent_deduction: Decimal
    adjustment_amount: Decimal
    status: str
    employee_name: str | None = None

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


class AttendanceClockInRequest(BaseModel):
    company_id: UUID
    employee_id: UUID


class AttendanceClockOutRequest(BaseModel):
    company_id: UUID
    employee_id: UUID


class AttendanceManualRequest(BaseModel):
    company_id: UUID
    employee_id: UUID
    work_date: date
    clock_in: datetime | None = None
    clock_out: datetime | None = None
    break_minutes: int = Field(default=60, ge=0)
    leave_type: str = Field(default="none")
    note: str | None = None


class AttendanceResponse(BaseModel):
    attendance_id: UUID
    employee_id: UUID
    company_id: UUID
    work_date: date
    clock_in: datetime | None = None
    clock_out: datetime | None = None
    break_minutes: int
    work_minutes: int
    overtime_minutes: int
    leave_type: str
    note: str | None = None
    employee_name: str | None = None

    model_config = {"from_attributes": True}


class ExpenseItemCreate(BaseModel):
    expense_date: date
    category: str = Field(description="transport, meal, accommodation, supplies, entertainment, other")
    description: str
    amount: Decimal = Field(ge=0)


class ExpenseReportCreate(BaseModel):
    company_id: UUID
    employee_id: UUID
    report_date: date
    title: str
    note: str | None = None
    items: list[ExpenseItemCreate]


class ExpenseItemResponse(BaseModel):
    item_id: UUID
    expense_date: date
    category: str
    description: str
    amount: Decimal

    model_config = {"from_attributes": True}


class ExpenseReportResponse(BaseModel):
    report_id: UUID
    employee_id: UUID
    company_id: UUID
    report_date: date
    title: str
    total_amount: Decimal
    status: str
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    note: str | None = None
    employee_name: str | None = None
    items: list[ExpenseItemResponse] = []

    model_config = {"from_attributes": True}


class InvoiceLineCreate(BaseModel):
    description: str
    quantity: Decimal = Field(default=Decimal("1"), ge=0)
    unit_price: Decimal = Field(ge=0)


class InvoiceCreate(BaseModel):
    company_id: UUID
    partner_id: UUID | None = None
    invoice_number: str
    invoice_date: date
    due_date: date
    tax_rate: Decimal = Field(default=Decimal("10.00"), ge=0, le=100)
    note: str | None = None
    lines: list[InvoiceLineCreate]


class InvoiceLineResponse(BaseModel):
    line_id: UUID
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal

    model_config = {"from_attributes": True}


class InvoiceResponse(BaseModel):
    invoice_id: UUID
    company_id: UUID
    partner_id: UUID | None = None
    invoice_number: str
    invoice_date: date
    due_date: date
    subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    status: str
    note: str | None = None
    partner_name: str | None = None
    lines: list[InvoiceLineResponse] = []

    model_config = {"from_attributes": True}


class TaxReturnCalculateRequest(BaseModel):
    company_id: UUID
    tax_year: int
    filing_type: str = Field(default="general", description="general or simplified")
    tax_adjustment: Decimal = Field(default=Decimal("0"))


class TaxReturnResponse(BaseModel):
    return_id: UUID
    company_id: UUID
    tax_year: int
    filing_type: str
    taxable_sales: Decimal
    non_taxable_sales: Decimal
    export_taxable_sales: Decimal
    total_sales: Decimal
    purchases_subject_to_tax: Decimal
    purchases_not_subject_to_tax: Decimal
    total_purchases: Decimal
    output_tax: Decimal
    input_tax: Decimal
    tax_adjustment: Decimal
    tax_payable: Decimal
    status: str
    note: str | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Paginated Response Types (ページネーション統一)
# ---------------------------------------------------------------------------

class InvoiceListResponse(BaseModel):
    items: list[InvoiceResponse]
    total: int
    page: int
    page_size: int


class ExpenseListResponse(BaseModel):
    items: list[ExpenseReportResponse]
    total: int
    page: int
    page_size: int


class PayrollListResponse(BaseModel):
    items: list[PayrollRecordResponse]
    total: int
    page: int
    page_size: int


class LaborInsuranceEmployeeResponse(BaseModel):
    employee_id: UUID
    employee_name: str
    gross_monthly_pay: Decimal
    employment_insurance_employee: Decimal
    employment_insurance_employer: Decimal
    workers_comp_employer: Decimal
    total_employee: Decimal
    total_employer: Decimal
    total_premium: Decimal

    model_config = {"from_attributes": True}


class LaborInsuranceSummaryResponse(BaseModel):
    company_id: UUID
    target_year: int
    target_month: int
    business_type: str
    workers_comp_rate: Decimal
    employee_count: int
    total_employee_premium: Decimal
    total_employer_premium: Decimal
    total_premium: Decimal
    items: list[LaborInsuranceEmployeeResponse]


class PartnerListResponse(BaseModel):
    items: list[PartnerResponse]
    total: int
    page: int
    page_size: int


class AuditLogResponse(BaseModel):
    log_id: UUID
    user_id: UUID | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    method: str
    path: str
    status_code: int
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


class AuditLedgerImbalanceEntry(BaseModel):
    journal_header_id: UUID
    debit_sum: Decimal
    credit_sum: Decimal
    difference: Decimal


class AuditLedgerBalanceCheckResponse(BaseModel):
    headers_checked: int
    imbalanced_count: int
    total_debit: Decimal
    total_credit: Decimal
    imbalanced_entries: list[AuditLedgerImbalanceEntry]


class AuditLedgerCacheDriftEntry(BaseModel):
    account_id: UUID
    year: int
    month: int
    expected_debit: Decimal
    expected_credit: Decimal
    cached_debit: Decimal
    cached_credit: Decimal


class AuditLedgerCacheDriftResponse(BaseModel):
    rows_checked: int
    drift_count: int
    drift_entries: list[AuditLedgerCacheDriftEntry]


class LedgerCheckRequest(BaseModel):
    company_id: UUID
    target_date: date


class LedgerCheckResponse(BaseModel):
    status: str
    balance_check: AuditLedgerBalanceCheckResponse
    cache_drift_check: AuditLedgerCacheDriftResponse


class AuditInspectRequest(BaseModel):
    journal_header_id: UUID


class AuditDetectionResponse(BaseModel):
    risk_level: str
    category: str
    reason: str


class YearEndListResponse(BaseModel):
    items: list[YearEndAdjustmentResponse]
    total: int
    page: int
    page_size: int


class BonusListResponse(BaseModel):
    items: list[BonusRecordResponse]
    total: int
    page: int
    page_size: int


class TaxReturnListResponse(BaseModel):
    items: list[TaxReturnResponse]
    total: int
    page: int
    page_size: int


class TaxForecastResponse(BaseModel):
    forecasted_profit_before_tax: Decimal
    estimated_taxable_income: Decimal
    estimated_tax_amount: Decimal
    tax_risk_warnings: list[str]


class EmployeeListResponse(BaseModel):
    items: list[EmployeeResponse]
    total: int
    page: int
    page_size: int


class AttendanceListResponse(BaseModel):
    items: list[AttendanceResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Notification schemas
# ---------------------------------------------------------------------------

class NotificationResponse(BaseModel):
    notification_id: UUID
    company_id: UUID | None = None
    user_id: UUID | None = None
    category: str
    priority: str
    title: str
    body: str
    action_url: str | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    page: int
    page_size: int


class NotificationCreate(BaseModel):
    company_id: UUID | None = None
    user_id: UUID | None = None
    category: str = Field(max_length=50)
    priority: str = Field(default="normal", max_length=20)
    title: str = Field(max_length=200)
    body: str
    action_url: str | None = None


class NotificationPreferenceResponse(BaseModel):
    preference_id: UUID
    user_id: UUID
    category: str
    channel_inapp: bool
    channel_email: bool
    channel_push: bool
    channel_webhook: bool

    model_config = {"from_attributes": True}


class NotificationPreferenceUpdate(BaseModel):
    channel_inapp: bool | None = None
    channel_email: bool | None = None
    channel_push: bool | None = None
    channel_webhook: bool | None = None


class WebhookEndpointCreate(BaseModel):
    company_id: UUID
    target_url: str
    secret_token: str
    subscribed_events: list[str]


class WebhookEndpointResponse(BaseModel):
    endpoint_id: UUID
    company_id: UUID
    target_url: str
    subscribed_events: list[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryResponse(BaseModel):
    delivery_id: UUID
    endpoint_id: UUID
    event_type: str
    status: str
    attempt_count: int
    response_status: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduledJobCreate(BaseModel):
    company_id: UUID
    job_type: str
    frequency: str
    run_hour: int = Field(ge=0, le=23)
    run_day: int | None = None
    priority: int = 100
    payload: dict[str, object] | None = None


class ScheduledJobResponse(BaseModel):
    scheduled_job_id: UUID
    company_id: UUID
    job_type: str
    frequency: str
    run_hour: int
    run_day: int | None = None
    priority: int
    payload: dict[str, object] | None = None
    is_active: bool
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobExecutionResponse(BaseModel):
    job_execution_id: UUID
    scheduled_job_id: UUID | None = None
    job_type: str
    status: str
    priority: int
    attempt_count: int
    scheduled_for: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OfficeTaskGenerateRequest(BaseModel):
    company_id: UUID
    scope: str = Field(description="'monthly' or 'daily'")
    target_year: int | None = None
    target_month: int | None = None
    target_date: date | None = None
    phase: str | None = None


class OfficeTaskResponse(BaseModel):
    task_id: UUID
    company_id: UUID
    task_type: str
    title: str
    status: str
    assigned_to: UUID | None = None
    due_date: date | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OfficeTaskStatusUpdate(BaseModel):
    status: str


class BudgetLineCreate(BaseModel):
    account_id: UUID
    month: int = Field(ge=1, le=12)
    budgeted_amount: Decimal = Field(ge=0)


class BudgetCreate(BaseModel):
    company_id: UUID
    fiscal_year: int = Field(ge=2000, le=2999)
    name: str = Field(max_length=200)
    lines: list[BudgetLineCreate] = Field(default_factory=list)


class BudgetLineResponse(BaseModel):
    budget_line_id: UUID
    account_id: UUID
    month: int
    budgeted_amount: Decimal

    model_config = {"from_attributes": True}


class BudgetResponse(BaseModel):
    budget_id: UUID
    company_id: UUID
    fiscal_year: int
    name: str
    status: str
    lines: list[BudgetLineResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class BudgetVarianceLine(BaseModel):
    account_id: UUID
    account_code: str
    account_name: str
    budgeted_amount: Decimal
    actual_amount: Decimal
    variance_amount: Decimal
    variance_rate: Decimal
    execution_rate: Decimal
    is_over_budget: bool


class BudgetVarianceResponse(BaseModel):
    budget_id: UUID
    fiscal_year: int
    budgeted_total: Decimal
    actual_total: Decimal
    variance_total: Decimal
    execution_rate: Decimal
    over_budget_count: int
    line_count: int
    lines: list[BudgetVarianceLine]


class BankReconcileRequest(BaseModel):
    company_id: UUID
    bank_account_id: UUID | None = None
    date_from: date | None = None
    date_to: date | None = None


class BankReconciliationCandidate(BaseModel):
    source_id: UUID
    source_type: str
    source_date: date
    amount: Decimal
    score: Decimal
    reason: str


class BankReconciliationItem(BaseModel):
    statement_detail_id: UUID
    candidates: list[BankReconciliationCandidate]


class BankAccountCreate(BaseModel):
    company_id: UUID
    bank_code: str = Field(min_length=4, max_length=4)
    branch_code: str = Field(min_length=3, max_length=3)
    account_type: str
    account_no_encrypted: bytes
    account_name: str = Field(max_length=100)
    account_name_kana: str = Field(max_length=40)
    currency_code: str = Field(default="JPY", min_length=3, max_length=3)


class BankAccountResponse(BaseModel):
    bank_account_id: UUID
    company_id: UUID
    bank_code: str
    branch_code: str
    account_type: str
    account_name: str
    account_name_kana: str
    currency_code: str
    auto_fetch_enabled: bool

    model_config = {"from_attributes": True}


class PaymentRequestCreate(BaseModel):
    company_id: UUID
    partner_id: UUID | None = None
    payment_date: date
    payment_amount: Decimal = Field(gt=0)
    bank_account_id: UUID | None = None
    dest_bank_code: str | None = Field(default=None, max_length=4)
    dest_branch_code: str | None = Field(default=None, max_length=3)
    dest_account_type: str | None = Field(default=None, max_length=10)
    dest_account_no: str | None = Field(default=None, max_length=7)
    dest_account_name_kana: str | None = Field(default=None, max_length=30)


class PaymentRequestResponse(BaseModel):
    payment_request_id: UUID
    company_id: UUID
    partner_id: UUID | None
    payment_date: date
    payment_amount: Decimal
    bank_account_id: UUID | None
    dest_bank_code: str | None
    dest_branch_code: str | None
    dest_account_type: str | None
    dest_account_no: str | None
    dest_account_name_kana: str | None
    status: str

    model_config = {"from_attributes": True}


class ZenginExportRequest(BaseModel):
    company_id: UUID
    payment_date: date
    bank_account_id: UUID
    payment_request_ids: list[UUID] | None = None


class ArchivedDocumentCreate(BaseModel):
    company_id: UUID
    transaction_date: date
    transaction_amount: Decimal
    counterparty_name: str = Field(max_length=255)
    document_type: str = Field(default="other", max_length=50)


class ArchivedDocumentResponse(BaseModel):
    document_id: UUID
    company_id: UUID
    file_path: str
    file_extension: str
    file_hash: str
    file_size: int
    transaction_date: date
    transaction_amount: Decimal
    counterparty_name: str
    document_type: str
    timestamp_token: str | None = None
    timestamp_verified_at: datetime | None = None
    journal_header_id: UUID | None = None
    created_by: UUID
    created_at: datetime
    is_deleted: bool

    model_config = {"from_attributes": True}


class CashflowForecastRequest(BaseModel):
    company_id: UUID
    as_of: date
    horizon_days: list[int] = Field(default_factory=lambda: [7, 30, 90, 365])


class CashflowForecastBucket(BaseModel):
    horizon_days: int
    inflows: Decimal
    outflows: Decimal
    net_cashflow: Decimal


class CashflowForecastResponse(BaseModel):
    company_id: UUID
    as_of: date
    buckets: list[CashflowForecastBucket]
