from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.labor_insurance import DEFAULT_WORKERS_COMPENSATION_RATE


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
    # Business constraints (nonzero amount, nonnegative tax) are enforced by
    # ValidationEngine so violations surface as domain VAL-xxx errors, not 422s.
    amount: Decimal
    tax_amount: Decimal = Decimal("0")
    description: str | None = None


class JournalCreate(BaseModel):
    company_id: UUID
    transaction_date: date
    voucher_type: str = Field(default="transfer", pattern="^(transfer|receipt|payment)$")
    summary: str | None = None
    # Minimum-line and balance rules are enforced by ValidationEngine (VAL-002/001).
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
    url: str = Field(max_length=500)
    # HMAC-SHA256の鍵として十分なエントロピーを持たせるため32文字以上を要求する。
    secret: str = Field(min_length=32, max_length=200)
    subscribed_events: list[str] = Field(default_factory=lambda: ["*"])
    company_id: UUID | None = None
    description: str | None = Field(default=None, max_length=200)


class WebhookEndpointResponse(BaseModel):
    webhook_endpoint_id: UUID
    company_id: UUID | None = None
    url: str
    subscribed_events: list[str]
    description: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryResponse(BaseModel):
    webhook_delivery_id: UUID
    webhook_endpoint_id: UUID
    event_type: str
    status: str
    attempt_count: int
    max_attempts: int
    last_status_code: int | None = None
    last_error: str | None = None
    next_retry_at: datetime | None = None
    delivered_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BankStatementLineResponse(BaseModel):
    bank_statement_line_id: UUID
    transaction_date: date
    value_date: date | None = None
    direction: str
    amount: Decimal
    balance: Decimal | None = None
    description: str | None = None
    counterparty_name: str | None = None
    is_reconciled: bool
    reconciled_journal_line_id: UUID | None = None
    reconciled_at: datetime | None = None
    source: str

    model_config = {"from_attributes": True}


class BankImportResponse(BaseModel):
    imported: int
    lines: list[BankStatementLineResponse]


class AutoReconcileRequest(BaseModel):
    bank_account_id: UUID
    date_tolerance_days: int = Field(default=3, ge=0, le=31)
    min_score: float = Field(default=0.6, ge=0.0, le=1.0)
    max_fee: Decimal = Field(default=Decimal("0"), ge=0, le=100000)


class AutoReconcileResponse(BaseModel):
    total_unreconciled: int
    matched: int
    unmatched: int


class ManualMatchRequest(BaseModel):
    journal_line_id: UUID


class AuditDetectionResponse(BaseModel):
    audit_detection_log_id: UUID
    company_id: UUID
    journal_header_id: UUID | None = None
    risk_level: str
    category: str
    message: str
    details: dict | None = None
    status: str
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditScanResponse(BaseModel):
    scanned: int
    detections_created: int


class AuditDetectionStatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|confirmed|dismissed)$")


class TaxAdjustmentRuleCreate(BaseModel):
    name: str = Field(max_length=100)
    adjustment_type: str = Field(pattern="^(addition|subtraction)$")
    calculation_method: str = Field(pattern="^(fixed|rate|excess_over_limit)$")
    rate: Decimal | None = None
    limit_amount: Decimal | None = None
    fixed_amount: Decimal | None = None
    target_account_code: str | None = Field(default=None, max_length=20)


class TaxAdjustmentRuleResponse(BaseModel):
    tax_adjustment_rule_id: UUID
    company_id: UUID
    name: str
    adjustment_type: str
    calculation_method: str
    rate: Decimal | None = None
    limit_amount: Decimal | None = None
    fixed_amount: Decimal | None = None
    target_account_code: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class TaxAdjustmentComputeRequest(BaseModel):
    accounting_income: Decimal
    base_amounts: dict[str, Decimal] = Field(default_factory=dict)


class TaxAdjustmentLineResult(BaseModel):
    rule_id: str
    name: str
    adjustment_type: str
    amount: Decimal


class TaxAdjustmentComputeResponse(BaseModel):
    accounting_income: Decimal
    taxable_income: Decimal
    total_additions: Decimal
    total_subtractions: Decimal
    adjustments: list[TaxAdjustmentLineResult]


class ArchivedDocumentResponse(BaseModel):
    archived_document_id: UUID
    company_id: UUID
    document_type: str
    file_name: str
    file_hash: str
    file_size: int
    mime_type: str | None = None
    storage_path: str
    transaction_date: date
    amount: Decimal | None = None
    counterparty_name: str | None = None
    linked_journal_header_id: UUID | None = None
    superseded_by_id: UUID | None = None
    registered_at: datetime

    model_config = {"from_attributes": True}


class DocumentVerifyResponse(BaseModel):
    archived_document_id: str
    is_valid: bool
    expected_hash: str
    actual_hash: str


class ApprovalPolicyCreate(BaseModel):
    document_type: str = Field(max_length=30)
    approver_role: str = Field(max_length=50)
    step_order: int = Field(default=1, ge=1)
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None


class ApprovalPolicyResponse(BaseModel):
    approval_policy_id: UUID
    company_id: UUID
    document_type: str
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    approver_role: str
    step_order: int
    is_active: bool

    model_config = {"from_attributes": True}


class ApprovalStepsResponse(BaseModel):
    document_type: str
    amount: Decimal
    required_steps: list[str]


class SecurityPolicyUpdate(BaseModel):
    require_mfa: bool | None = None
    allowed_ip_cidrs: list[str] | None = None
    session_timeout_minutes: int | None = Field(default=None, ge=5, le=1440)
    password_min_length: int | None = Field(default=None, ge=8, le=128)
    max_failed_attempts: int | None = Field(default=None, ge=1, le=20)


class SecurityPolicyResponse(BaseModel):
    tenant_security_policy_id: UUID
    tenant_id: UUID
    require_mfa: bool
    allowed_ip_cidrs: list[str]
    session_timeout_minutes: int
    password_min_length: int
    max_failed_attempts: int

    model_config = {"from_attributes": True}


class AiInferenceLogCreate(BaseModel):
    company_id: UUID
    source_type: str = Field(max_length=30)
    suggestion: dict
    confidence: Decimal = Field(ge=0, le=1)
    input_summary: str | None = None
    provider: str | None = None
    journal_header_id: UUID | None = None


class AiInferenceLogResponse(BaseModel):
    ai_inference_log_id: UUID
    company_id: UUID
    source_type: str
    input_summary: str | None = None
    suggestion: dict
    confidence: Decimal
    provider: str | None = None
    applied: bool
    correction_diff: dict | None = None
    journal_header_id: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AiInferenceApplyRequest(BaseModel):
    final: dict | None = None


class AiInferenceStatsResponse(BaseModel):
    total: int
    applied: int
    acceptance_rate: float
    corrected: int
    correction_rate: float
    avg_confidence: float


class AiCalibrationBand(BaseModel):
    band: str
    count: int
    avg_confidence: float | None = None
    observed_accuracy: float | None = None
    gap: float | None = None


class AiCalibrationResponse(BaseModel):
    applied_total: int
    ece: float
    bands: list[AiCalibrationBand]


class OfficeTaskCreate(BaseModel):
    title: str = Field(max_length=200)
    task_type: str = Field(max_length=40)
    due_date: date | None = None
    assigned_to: UUID | None = None
    period: str | None = Field(default=None, max_length=7)


class OfficeTaskResponse(BaseModel):
    office_task_id: UUID
    company_id: UUID
    title: str
    task_type: str
    assigned_to: UUID | None = None
    due_date: date | None = None
    status: str
    period: str | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OfficeTaskGenerateRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class OfficeTaskStatusUpdate(BaseModel):
    status: str = Field(pattern="^(todo|in_progress|done)$")


class OfficeTaskProgressResponse(BaseModel):
    total: int
    todo: int
    in_progress: int
    done: int
    completion_rate: float


# --- main由来の独立ドメイン用スキーマ（予算/銀行/支払/ジョブ/税務/賞与/社保等） ---

class InvoiceTaxLineInput(BaseModel):
    amount: Decimal = Field(ge=0)
    tax_rate: Decimal


class InvoiceTaxComputeRequest(BaseModel):
    lines: list[InvoiceTaxLineInput]


class InvoiceTaxRateBreakdownResponse(BaseModel):
    tax_rate: Decimal
    taxable_base: Decimal
    tax: Decimal

    model_config = {"from_attributes": True}


class InvoiceTaxComputeResponse(BaseModel):
    by_rate: list[InvoiceTaxRateBreakdownResponse]
    total_taxable: Decimal
    total_tax: Decimal
    total_amount: Decimal


class QualifiedInvoiceLineInput(BaseModel):
    description: str
    tax_rate: Decimal


class QualifiedInvoiceTaxByRateInput(BaseModel):
    tax_rate: Decimal
    tax_amount: Decimal


class QualifiedInvoiceCheckRequest(BaseModel):
    issuer_name: str
    registration_number: str
    transaction_date: date | None = None
    recipient_name: str
    line_items: list[QualifiedInvoiceLineInput]
    tax_by_rate: list[QualifiedInvoiceTaxByRateInput]


class QualifiedInvoiceCheckResponse(BaseModel):
    is_valid: bool
    missing_fields: list[str]
    registration_number_valid: bool


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


class TaxForecastResponse(BaseModel):
    forecasted_profit_before_tax: Decimal
    estimated_taxable_income: Decimal
    estimated_tax_amount: Decimal
    tax_risk_warnings: list[str]


class SocialInsuranceBreakdownResponse(BaseModel):
    total: Decimal
    employee: Decimal
    employer: Decimal


class SocialInsurancePremiumResponse(BaseModel):
    standard_monthly_remuneration: Decimal
    health_rate: Decimal
    care_rate: Decimal
    care_applicable: bool
    health: SocialInsuranceBreakdownResponse
    care: SocialInsuranceBreakdownResponse
    pension: SocialInsuranceBreakdownResponse
    total_employee: Decimal
    total_employer: Decimal
    total_premium: Decimal


class BonusEmploymentInsuranceResponse(BaseModel):
    employee_premium: Decimal
    employer_premium: Decimal
    total_premium: Decimal
    employee_rate: Decimal
    employer_rate: Decimal


class BonusWithholdingTaxResponse(BaseModel):
    bonus_after_social_insurance: Decimal
    bonus_tax_rate: Decimal
    prior_month_salary_after_social_insurance: Decimal | None = None
    withholding_tax: Decimal | None = None
    requires_monthly_table: bool
    reason: str


class YearEndAdjustmentCalcResponse(BaseModel):
    salary_income_deduction: Decimal
    salary_income: Decimal
    taxable_income: Decimal
    calculated_income_tax: Decimal
    housing_loan_credit: Decimal
    year_adjusted_income_tax: Decimal
    year_tax: Decimal
    withheld_tax_total: Decimal
    refund: Decimal
    additional_collection: Decimal


class LegalLedgerCheckRequest(BaseModel):
    ledger_type: str
    present_fields: list[str]


class LegalLedgerCheckResponse(BaseModel):
    ledger_type: str
    required_fields: list[str]
    missing_fields: list[str]
    compliant: bool


class SocialInsuranceExemptionResponse(BaseModel):
    exempt: bool
    reason: str


class DependentEligibilityResponse(BaseModel):
    income_limit: Decimal
    income_requirement_met: bool
    relationship_requirement_met: bool
    eligible: bool
    reason: str


class MinimumWageCheckResponse(BaseModel):
    effective_hourly_wage: Decimal
    minimum_hourly_wage: Decimal
    meets_minimum: bool
    shortfall_per_hour: Decimal


class MonthlyPayslipResponse(BaseModel):
    taxable_earnings: Decimal
    non_taxable_commute_allowance: Decimal
    total_earnings: Decimal
    social_insurance: SocialInsurancePremiumResponse
    social_insurance_employee: Decimal
    employment_insurance_employee: Decimal
    income_tax: Decimal
    residence_tax: Decimal
    other_deductions: Decimal
    total_deductions: Decimal
    net_pay: Decimal


class RetirementIncomeTaxResponse(BaseModel):
    years_of_service: int
    retirement_income_deduction: Decimal
    taxable_base: Decimal
    taxable_retirement_income: Decimal
    income_tax_base: Decimal
    statement_submitted: bool
    withholding_tax: Decimal


class MonthlyOvertimeInput(BaseModel):
    overtime_hours: Decimal
    holiday_work_hours: Decimal = Decimal("0")


class OvertimeLimitCheckRequest(BaseModel):
    months: list[MonthlyOvertimeInput]


class OvertimeLimitCheckResponse(BaseModel):
    annual_overtime_total: Decimal
    annual_limit_exceeded: bool
    months_over_45_count: int
    months_over_45_limit_exceeded: bool
    single_month_combined_exceeded: bool
    multi_month_average_exceeded: bool
    compliant: bool
    violations: list[str]


class PaidLeaveGrantResponse(BaseModel):
    granted_days: int
    is_proportional: bool
    meets_attendance_requirement: bool
    mandatory_5day_designation: bool


class CommuteAllowanceResponse(BaseModel):
    mode: str
    monthly_allowance: Decimal
    non_taxable_limit: Decimal
    non_taxable: Decimal
    taxable: Decimal


class ResidenceTaxMonthlyAmountResponse(BaseModel):
    month: int
    amount: Decimal


class ResidenceTaxResponse(BaseModel):
    annual_tax: Decimal
    first_month_amount: Decimal
    ordinary_month_amount: Decimal
    monthly_amounts: list[ResidenceTaxMonthlyAmountResponse]
    total: Decimal


class BonusNetPayResponse(BaseModel):
    gross_bonus: Decimal
    standard_bonus: Decimal
    health_standard_bonus: Decimal
    pension_standard_bonus: Decimal
    social_insurance: SocialInsurancePremiumResponse
    employment_insurance_employee: Decimal
    bonus_after_social_insurance: Decimal
    withholding_tax: Decimal | None = None
    requires_monthly_table: bool
    reason: str
    total_employee_deductions: Decimal
    net_pay: Decimal | None = None


class LaborInsuranceInstallmentResponse(BaseModel):
    estimated_premium: Decimal
    threshold: Decimal
    both_insurances: bool
    entrusted: bool
    eligible: bool
    installment_count: int
    installments: list[Decimal]
    note: str


class SanteiMonthInput(BaseModel):
    payment_basis_days: int
    currency_remuneration: Decimal
    in_kind_remuneration: Decimal


class SanteiEmployeeInput(BaseModel):
    insured_number: str
    name: str
    birth_date: date
    previous_health_standard: Decimal
    previous_pension_standard: Decimal
    applicable_year: int
    applicable_month: int
    months: list[SanteiMonthInput]


class SanteiExportRequest(BaseModel):
    employees: list[SanteiEmployeeInput]


class QualificationAcquisitionEmployeeInput(BaseModel):
    insured_number: str
    name: str
    birth_date: date
    qualification_date: date
    estimated_monthly_remuneration: Decimal


class QualificationAcquisitionExportRequest(BaseModel):
    employees: list[QualificationAcquisitionEmployeeInput]


class LaborInsuranceAnnualUpdateRequest(BaseModel):
    prior_wage_total: Decimal
    estimated_wage_total: Decimal
    business_type: str
    declared_prior_estimate: Decimal
    workers_comp_rate: Decimal = DEFAULT_WORKERS_COMPENSATION_RATE


class BonusEmployeeInput(BaseModel):
    insured_number: str
    name: str
    payment_date: date
    bonus_amount: Decimal
    fiscal_ytd_standard_bonus: Decimal = Decimal("0")
    same_month_prior_standard_bonus: Decimal = Decimal("0")


class BonusExportRequest(BaseModel):
    employees: list[BonusEmployeeInput]


class MonthlyRevisionMonthInput(BaseModel):
    payment_basis_days: int
    remuneration: Decimal


class MonthlyRevisionEmployeeInput(BaseModel):
    insured_number: str
    name: str
    previous_health_standard: Decimal
    previous_pension_standard: Decimal
    fixed_wage_changed: bool
    months: list[MonthlyRevisionMonthInput]


class MonthlyRevisionExportRequest(BaseModel):
    employees: list[MonthlyRevisionEmployeeInput]


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


class JobExecutionComplete(BaseModel):
    success: bool
    error_message: str | None = None


class HealthSummaryResponse(BaseModel):
    total: int
    failed: int
    dead: int
    failure_rate: float
    level: str


class OperationsHealthResponse(BaseModel):
    company_id: UUID
    overall_level: str
    jobs: HealthSummaryResponse
    webhooks: HealthSummaryResponse
    overdue_tasks: int


class EventJournalDraftRequest(BaseModel):
    event_type: str
    amount: Decimal = Field(gt=0)
    tax_rate: Decimal = Decimal("0.10")
    is_tax_inclusive: bool = True


class JournalLineDraftResponse(BaseModel):
    account_role: str
    debit: Decimal
    credit: Decimal


class EventJournalDraftResponse(BaseModel):
    event_type: str
    description: str
    total_debit: Decimal
    total_credit: Decimal
    lines: list[JournalLineDraftResponse]


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


class DenchouElectronicCheckRequest(BaseModel):
    has_timestamp: bool = False
    has_correction_deletion_history: bool = False
    has_operational_rules: bool = False
    has_display_device: bool = True
    can_search_by_date: bool = False
    can_search_by_amount: bool = False
    can_search_by_counterparty: bool = False
    can_search_by_range: bool = False
    can_search_by_combination: bool = False
    base_period_sales: Decimal = Decimal("0")
    can_provide_download: bool = False


class DenchouElectronicCheckResponse(BaseModel):
    authenticity_met: bool
    visibility_met: bool
    required_search_level: str
    search_requirement_met: bool
    compliant: bool
    missing_requirements: list[str]


class DenchouScannerCheckRequest(BaseModel):
    resolution_dpi: int
    is_color: bool = True
    is_general_document: bool = False
    input_period_type: str = "prompt"
    days_until_input: int = 0
    has_operational_rules: bool = False
    has_timestamp: bool = False
    has_correction_deletion_history: bool = False
    has_display_device: bool = True
    can_search_by_date: bool = False
    can_search_by_amount: bool = False
    can_search_by_counterparty: bool = False
    can_search_by_range: bool = False
    can_search_by_combination: bool = False


class DenchouScannerCheckResponse(BaseModel):
    resolution_met: bool
    color_met: bool
    input_period_met: bool
    authenticity_met: bool
    visibility_met: bool
    compliant: bool
    missing_requirements: list[str]


class HighAgeBenefitRequest(BaseModel):
    age: int
    insured_months: int
    wage_at_60: Decimal
    current_wage: Decimal


class HighAgeBenefitResponse(BaseModel):
    eligible: bool
    reduction_ratio: Decimal
    benefit_amount: Decimal
    reason: str


class InjuryAllowanceRequest(BaseModel):
    avg_standard_monthly: Decimal
    insured_months: int
    absent_days: int
    waiting_completed: bool = False
    daily_remuneration: Decimal = Decimal("0")


class MaternityAllowanceRequest(BaseModel):
    avg_standard_monthly: Decimal
    insured_months: int
    days_before_birth: int
    days_after_birth: int
    multiple_pregnancy: bool = False
    daily_remuneration: Decimal = Decimal("0")


class HealthInsuranceBenefitResponse(BaseModel):
    daily_benefit: Decimal
    effective_daily_benefit: Decimal
    payable_days: int
    total_amount: Decimal


class ShortTimeInsuranceRequest(BaseModel):
    weekly_hours: Decimal
    monthly_wage: Decimal
    employment_over_2_months: bool
    is_student: bool
    company_insured_count: int
    labor_agreement: bool = False
    meets_three_quarters_standard: bool = False


class ShortTimeInsuranceResponse(BaseModel):
    covered: bool
    is_specified_workplace: bool
    meets_hours: bool
    meets_wage: bool
    meets_employment_period: bool
    not_student: bool
    reasons: list[str]


class ChildcareLeaveBenefitRequest(BaseModel):
    wage_total_6m: Decimal
    insured_months: int
    payment_days: int = 30
    cumulative_days_before: int = 0
    wage_paid_during_leave: Decimal = Decimal("0")


class ChildcareLeaveBenefitResponse(BaseModel):
    eligible: bool
    daily_wage: Decimal
    benefit_rate: Decimal
    benefit_amount: Decimal
    reason: str


class CaregiverLeaveBenefitRequest(BaseModel):
    wage_total_6m: Decimal
    insured_months: int
    payment_days: int = 30
    cumulative_days_before: int = 0
    wage_paid_during_leave: Decimal = Decimal("0")


class CaregiverLeaveBenefitResponse(BaseModel):
    eligible: bool
    daily_wage: Decimal
    payable_days: int
    benefit_amount: Decimal
    reason: str


class WorkersAccidentLeaveRequest(BaseModel):
    daily_wage_base: Decimal
    absent_days: int
    waiting_completed: bool = False
    daily_partial_wage: Decimal = Decimal("0")


class WorkersAccidentLeaveResponse(BaseModel):
    payable_days: int
    daily_compensation: Decimal
    daily_special: Decimal
    total_compensation: Decimal
    total_special: Decimal
    total_benefit: Decimal


class HighCostMedicalRequest(BaseModel):
    total_medical_cost: Decimal
    self_paid: Decimal
    income_category: str
    multiple_treatment: bool = False


class HighCostMedicalResponse(BaseModel):
    self_pay_limit: Decimal
    high_cost_benefit: Decimal


class PostnatalLeaveBenefitRequest(BaseModel):
    wage_total_6m: Decimal
    insured_months: int
    leave_days: int
    cumulative_days_before: int = 0
    wage_paid_during_leave: Decimal = Decimal("0")


class PostnatalLeaveBenefitResponse(BaseModel):
    eligible: bool
    daily_wage: Decimal
    payable_days: int
    benefit_amount: Decimal
    reason: str


class PayrollWageImportRequest(BaseModel):
    csv_text: str
    business_type: str = "general"
    workers_comp_rate: Decimal = DEFAULT_WORKERS_COMPENSATION_RATE
    column_map: dict[str, str] | None = None


class PayrollWageImportResponse(BaseModel):
    row_count: int
    employee_count: int
    employment_insured_count: int
    workers_comp_wage_total: Decimal
    employment_wage_total: Decimal
    workers_comp_base: Decimal
    employment_base: Decimal
    workers_comp_premium: Decimal
    employment_premium: Decimal
    employment_employee_premium: Decimal
    employment_employer_premium: Decimal
    general_contribution: Decimal
    determined_premium: Decimal

    model_config = {"from_attributes": True}


class SalesReturnLineSchema(BaseModel):
    amount: Decimal
    tax_rate: Decimal


class SalesReturnTaxRequest(BaseModel):
    returns: list[SalesReturnLineSchema]


class SalesReturnRateBreakdownSchema(BaseModel):
    tax_rate: Decimal
    return_amount: Decimal
    deductible_tax: Decimal

    model_config = {"from_attributes": True}


class SalesReturnTaxResponse(BaseModel):
    by_rate: list[SalesReturnRateBreakdownSchema]
    total_return: Decimal
    total_deductible_tax: Decimal

    model_config = {"from_attributes": True}
