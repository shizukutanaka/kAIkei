import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    tenant_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    companies = relationship("Company", back_populates="tenant")
    users = relationship("User", back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="viewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant", back_populates="users")


class Company(Base):
    __tablename__ = "companies"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_code: Mapped[str] = mapped_column(String(50), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(300))
    tax_id: Mapped[str | None] = mapped_column(String(20))
    invoice_registration_number: Mapped[str | None] = mapped_column(String(20))
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    tax_method: Mapped[str] = mapped_column(String(30), default="general", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant", back_populates="companies")
    accounts = relationship("Account", back_populates="company")
    journal_headers = relationship("JournalHeader", back_populates="company")


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    account_code: Mapped[str] = mapped_column(String(20), nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    debit_credit: Mapped[str] = mapped_column(String(10), nullable=False)
    parent_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, server_default=func.current_date(), nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company", back_populates="accounts")
    sub_accounts = relationship("SubAccount", back_populates="account")
    journal_lines = relationship("JournalLine", back_populates="account")


class SubAccount(Base):
    __tablename__ = "sub_accounts"

    sub_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False)
    sub_account_code: Mapped[str] = mapped_column(String(20), nullable=False)
    sub_account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, server_default=func.current_date(), nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    account = relationship("Account", back_populates="sub_accounts")


class TaxRule(Base):
    __tablename__ = "tax_rules"

    tax_rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    tax_code: Mapped[str] = mapped_column(String(20), nullable=False)
    tax_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    tax_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_inclusive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, server_default=func.current_date(), nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class JournalHeader(Base):
    __tablename__ = "journal_headers"

    journal_header_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    journal_number: Mapped[str] = mapped_column(String(50), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    voucher_type: Mapped[str] = mapped_column(String(20), default="transfer", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)
    is_voided: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company", back_populates="journal_headers")
    lines = relationship("JournalLine", back_populates="header", cascade="all, delete-orphan")


class JournalLine(Base):
    __tablename__ = "journal_lines"

    journal_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_header_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_headers.journal_header_id"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    debit_credit: Mapped[str] = mapped_column(String(10), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False)
    sub_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sub_accounts.sub_account_id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tax_rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tax_rules.tax_rule_id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    header = relationship("JournalHeader", back_populates="lines")
    account = relationship("Account", back_populates="journal_lines")


class MonthlyBalance(Base):
    __tablename__ = "monthly_balances"

    balance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    debit_total: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    credit_total: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Budget(Base):
    """予算ヘッダー（会計年度単位）。"""
    __tablename__ = "budgets"

    budget_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company")
    lines = relationship("BudgetLine", back_populates="budget", cascade="all, delete-orphan")


class BudgetLine(Base):
    """予算明細（勘定科目×月単位）。"""
    __tablename__ = "budget_lines"

    budget_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budgets.budget_id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    budgeted_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    budget = relationship("Budget", back_populates="lines")
    account = relationship("Account")


class ApprovalWorkflow(Base):
    """承認ワークフロー定義。"""
    __tablename__ = "approval_workflows"

    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    trigger_type: Mapped[str] = mapped_column(String(30), default="amount_threshold", nullable=False)
    threshold_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    required_approver_roles: Mapped[str] = mapped_column(Text, default="approver,admin", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ApprovalLog(Base):
    """承認操作の監査ログ。"""
    __tablename__ = "approval_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_header_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_headers.journal_header_id"), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FixedAsset(Base):
    """固定資産。"""
    __tablename__ = "fixed_assets"

    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    asset_code: Mapped[str] = mapped_column(String(50), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_category: Mapped[str] = mapped_column(String(50), nullable=False)
    acquisition_date: Mapped[date] = mapped_column(Date, nullable=False)
    acquisition_cost: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    depreciation_method: Mapped[str] = mapped_column(String(20), default="straight_line", nullable=False)
    salvage_value: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    accumulated_depreciation: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.account_id"))
    is_disposed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    disposal_date: Mapped[date | None] = mapped_column(Date)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company")
    depreciation_records = relationship("DepreciationRecord", back_populates="asset")


class DepreciationRecord(Base):
    """減価償却レコード。"""
    __tablename__ = "depreciation_records"

    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fixed_assets.asset_id"), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    depreciation_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    accumulated_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    journal_header_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_headers.journal_header_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    asset = relationship("FixedAsset", back_populates="depreciation_records")


class IdempotencyRecord(Base):
    """冪等性保証用レコード。"""
    __tablename__ = "idempotency_records"

    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Employee(Base):
    """従業員マスタ。"""
    __tablename__ = "employees"

    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    employee_code: Mapped[str] = mapped_column(String(50), nullable=False)
    employee_name: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(100))
    employment_type: Mapped[str] = mapped_column(String(20), default="full_time", nullable=False)
    base_salary: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    termination_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company")
    payroll_records = relationship("PayrollRecord", back_populates="employee")


class PayrollRecord(Base):
    """給与計算レコード。"""
    __tablename__ = "payroll_records"

    payroll_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    payroll_year: Mapped[int] = mapped_column(Integer, nullable=False)
    payroll_month: Mapped[int] = mapped_column(Integer, nullable=False)
    base_salary: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"), nullable=False)
    overtime_pay: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    total_gross: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    income_tax: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    social_insurance: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    total_deductions: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    net_pay: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    employee = relationship("Employee", back_populates="payroll_records")
    company = relationship("Company")


class Partner(Base):
    """取引先マスタ。"""
    __tablename__ = "partners"

    partner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    partner_code: Mapped[str] = mapped_column(String(50), nullable=False)
    partner_name: Mapped[str] = mapped_column(String(200), nullable=False)
    partner_type: Mapped[str] = mapped_column(String(20), nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(10))
    address: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(200))
    contact_person: Mapped[str | None] = mapped_column(String(100))
    payment_terms: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company")


class BonusRecord(Base):
    """賞与計算レコード。"""
    __tablename__ = "bonus_records"

    bonus_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    bonus_year: Mapped[int] = mapped_column(Integer, nullable=False)
    bonus_term: Mapped[str] = mapped_column(String(20), nullable=False)
    bonus_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    bonus_base_months: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), nullable=False)
    performance_factor: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("1.00"), nullable=False)
    income_tax: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    social_insurance: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    total_deductions: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    net_pay: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    employee = relationship("Employee")
    company = relationship("Company")


class YearEndAdjustment(Base):
    """年末調整レコード。"""
    __tablename__ = "year_end_adjustments"

    adjustment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    adjustment_year: Mapped[int] = mapped_column(Integer, nullable=False)
    annual_salary: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    annual_bonus: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    total_gross: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    withholding_tax_total: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    estimated_annual_tax: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    social_insurance_total: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    dependents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dependent_deduction: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    adjustment_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    employee = relationship("Employee")
    company = relationship("Company")


class AttendanceRecord(Base):
    """勤怠記録。"""
    __tablename__ = "attendance_records"

    attendance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    clock_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clock_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    break_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    work_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leave_type: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    employee = relationship("Employee")
    company = relationship("Company")


class ExpenseReport(Base):
    """経費精算（ヘッダ）。"""
    __tablename__ = "expense_reports"

    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.employee_id"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="submitted", nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    employee = relationship("Employee")
    company = relationship("Company")
    items = relationship("ExpenseItem", back_populates="report", cascade="all, delete-orphan")


class ExpenseItem(Base):
    """経費精算明細。"""
    __tablename__ = "expense_items"

    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("expense_reports.report_id", ondelete="CASCADE"), nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    report = relationship("ExpenseReport", back_populates="items")


class Invoice(Base):
    """請求書（売上）。"""
    __tablename__ = "invoices"

    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    partner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("partners.partner_id"), nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("10.00"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company")
    partner = relationship("Partner")
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLine(Base):
    """請求書明細。"""
    __tablename__ = "invoice_lines"

    line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 3), default=Decimal("1"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(15, 4), nullable=False)

    invoice = relationship("Invoice", back_populates="lines")


class BankAccount(Base):
    """銀行口座。"""
    __tablename__ = "bank_accounts"

    bank_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    bank_code: Mapped[str] = mapped_column(String(4), nullable=False)
    branch_code: Mapped[str] = mapped_column(String(3), nullable=False)
    account_type: Mapped[str] = mapped_column(String(10), nullable=False)
    account_no_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_name_kana: Mapped[str] = mapped_column(String(40), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), default="JPY", nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, server_default=func.current_date(), nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    auto_fetch_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company")
    statement_details = relationship("BankStatementDetail", back_populates="bank_account")
    payment_requests = relationship("PaymentRequest", back_populates="bank_account")


class BankStatementDetail(Base):
    """銀行明細。"""
    __tablename__ = "bank_statement_details"

    statement_detail_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    bank_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bank_accounts.bank_account_id"), nullable=False)
    value_date: Mapped[date] = mapped_column(Date, nullable=False)
    withdraw_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"), nullable=False)
    deposit_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"), nullable=False)
    sender_name_kana: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_reconciled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reconciled_journal_header_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_headers.journal_header_id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    company = relationship("Company")
    bank_account = relationship("BankAccount", back_populates="statement_details")


class PaymentRequest(Base):
    """支払申請。"""
    __tablename__ = "payment_requests"

    payment_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    partner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("partners.partner_id"))
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bank_accounts.bank_account_id"))
    dest_bank_code: Mapped[str | None] = mapped_column(String(4))
    dest_branch_code: Mapped[str | None] = mapped_column(String(3))
    dest_account_type: Mapped[str | None] = mapped_column(String(10))
    dest_account_no: Mapped[str | None] = mapped_column(String(7))
    dest_account_name_kana: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    journal_header_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_headers.journal_header_id"))
    zengin_export_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company")
    partner = relationship("Partner")
    bank_account = relationship("BankAccount", back_populates="payment_requests")


class TaxReturn(Base):
    """消費税申告（年次）。"""
    __tablename__ = "tax_returns"

    return_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    filing_type: Mapped[str] = mapped_column(String(20), default="general", nullable=False)
    taxable_sales: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    non_taxable_sales: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    export_taxable_sales: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    total_sales: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    purchases_subject_to_tax: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    purchases_not_subject_to_tax: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    total_purchases: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    output_tax: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    input_tax: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    tax_adjustment: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    tax_payable: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="calculated", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company")


class AuditLog(Base):
    """操作証跡ログ（追記専用・改ざん検知対応）。"""
    __tablename__ = "audit_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    request_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PeriodClose(Base):
    """月次締切。"""
    __tablename__ = "period_closes"

    close_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company")


class Notification(Base):
    """通知（アプリ内/メール/プッシュ/チャット/Webhook）。"""
    __tablename__ = "notifications"

    notification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id"), nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.company_id"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User")


class NotificationPreference(Base):
    """ユーザーごとの通知設定。"""
    __tablename__ = "notification_preferences"

    preference_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_inapp: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    channel_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    channel_push: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    channel_webhook: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User")
