# kAIkei — データベース設計書（ER図・物理データモデル）

> 本ドキュメントはkAIkeiの全エンティティ・リレーション・DDLを定義する。
> Plan.mdのフェーズ1〜9で参照されるマスタデータモデルである。

---

## 1. ER図（テキスト表現）

```
┌──────────────┐       ┌──────────────────────┐       ┌──────────────────┐
│  tenants     │       │  companies           │       │  journal_headers  │
│──────────────│       │──────────────────────│       │──────────────────│
│ tenant_id PK │──1:N─││ company_id PK        │──1:N─││ journal_header_id│
│ tenant_name  │       │ tenant_id FK         │       │ company_id FK     │
│ plan_type    │       │ corporate_number     │       │ journal_no        │
│ created_at   │       │ invoice_reg_number   │       │ transaction_date  │
└──────────────┘       │ company_name         │       │ slip_type         │
                       │ fiscal_month_start   │       │ approval_status   │
                       │ tax_system_type      │       │ created_by FK     │
                       └─────────┬────────────┘       │ approved_by FK    │
                                 │                    │ is_voided         │
                                 │ 1:N                └────────┬──────────┘
                                 │                             │ 1:N
                       ┌─────────┴────────────┐       ┌────────┴──────────┐
                       │  (他マスタ群)         │       │  journal_lines    │
                       │  accounts            │       │──────────────────│
                       │  sub_accounts        │       │ journal_line_id PK│
                       │  departments         │       │ journal_header_id │
                       │  projects            │       │ entry_type        │
                       │  tax_rules           │       │ account_code      │
                       │  tax_adjustment_rules│       │ sub_account_code  │
                       │  fixed_assets        │       │ tax_type_code     │
                       │  bank_accounts       │       │ amount_excl_tax   │
                       │  approval_policies   │       │ tax_amount        │
                       │  archived_documents  │       │ amount_incl_tax   │
                       │  office_tasks        │       │ summary           │
                       │  employees           │       └──────────────────┘
                       │  users               │
                       │  roles               │
                       └──────────────────────┘
```

### 主要リレーション一覧

| 親テーブル | 子テーブル | カーディナリティ | 外部キー |
|-----------|-----------|----------------|---------|
| `tenants` | `companies` | 1:N | `tenant_id` |
| `companies` | `journal_headers` | 1:N | `company_id` |
| `journal_headers` | `journal_lines` | 1:N | `journal_header_id` (CASCADE) |
| `companies` | `fixed_assets` | 1:N | `company_id` |
| `companies` | `archived_documents` | 1:N | `company_id` |
| `companies` | `approval_policies` | 1:N | `company_id` |
| `companies` | `office_tasks` | 1:N | `company_id` |
| `companies` | `bank_accounts` | 1:N | `company_id` |
| `tenants` | `tenant_security_policies` | 1:1 | `tenant_id` |
| `tenants` | `idempotency_keys` | 1:N | `tenant_id` |
| `webhook_endpoints` | `webhook_deliveries` | 1:N | `endpoint_id` (CASCADE) |
| `companies` | `bank_statement_details` | 1:N | `company_id` |
| `companies` | `audit_detection_logs` | 1:N | `company_id` |
| `journal_headers` | `audit_detection_logs` | 1:N | `journal_header_id` |

---

## 2. テナント・ユーザー・ロール

### 2.1 tenants

```sql
CREATE TABLE tenants (
    tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_name VARCHAR(255) NOT NULL,
    plan_type VARCHAR(20) NOT NULL DEFAULT 'standard', -- 'trial', 'standard', 'enterprise'
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 2.2 users

```sql
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255), -- SSO利用時はNULL
    display_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tenant_email UNIQUE (tenant_id, email)
);

CREATE INDEX idx_users_tenant ON users(tenant_id);
```

### 2.3 roles

```sql
CREATE TABLE roles (
    role_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    role_name VARCHAR(100) NOT NULL, -- 'accounting_manager', 'approver', 'viewer' etc.
    role_code VARCHAR(50) NOT NULL,
    description TEXT,
    is_system_role BOOLEAN NOT NULL DEFAULT FALSE, -- システム標準ロールか
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tenant_role_code UNIQUE (tenant_id, role_code)
);
```

### 2.4 user_roles

```sql
CREATE TABLE user_roles (
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(company_id), -- NULL=全会社対象
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_id, company_id)
);
```

### 2.5 audit_trails（操作証跡）

```sql
CREATE TABLE audit_trails (
    trail_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    company_id UUID,
    action VARCHAR(50) NOT NULL, -- 'login', 'logout', 'create', 'update', 'delete', 'export', 'print', 'api_call', 'ai_approve'
    resource_type VARCHAR(50), -- 'journal', 'document', 'payment', 'master' etc.
    resource_id UUID,
    detail JSONB, -- 変更前後のスナップショット等
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_trails_tenant_time ON audit_trails(tenant_id, created_at DESC);
CREATE INDEX idx_audit_trails_resource ON audit_trails(resource_type, resource_id);
```

---

## 3. 会社・マスタ

### 3.1 companies

```sql
CREATE TABLE companies (
    company_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    corporate_number CHAR(13) UNIQUE,
    invoice_registration_number VARCHAR(14),
    company_name VARCHAR(255) NOT NULL,
    company_name_kana VARCHAR(255),
    fiscal_month_start INT NOT NULL DEFAULT 4,
    tax_system_type SMALLINT NOT NULL DEFAULT 1, -- 1:本則課税, 2:簡易課税, 3:2割特例
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_companies_tenant ON companies(tenant_id);
```

### 3.2 accounts（勘定科目マスタ）

```sql
CREATE TABLE accounts (
    account_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    account_code VARCHAR(10) NOT NULL,
    account_name VARCHAR(100) NOT NULL,
    account_type VARCHAR(20) NOT NULL, -- 'asset', 'liability', 'equity', 'revenue', 'expense'
    balance_type VARCHAR(10) NOT NULL DEFAULT 'debit', -- 'debit'(借方残), 'credit'(貸方残)
    is_valid BOOLEAN NOT NULL DEFAULT TRUE,
    valid_from DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to DATE,
    display_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_company_account_code UNIQUE (company_id, account_code, valid_from)
);

CREATE INDEX idx_accounts_lookup ON accounts(company_id, account_code, valid_from, valid_to);
```

### 3.3 sub_accounts（補助科目マスタ）

```sql
CREATE TABLE sub_accounts (
    sub_account_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    account_code VARCHAR(10) NOT NULL,
    sub_account_code VARCHAR(10) NOT NULL,
    sub_account_name VARCHAR(100) NOT NULL,
    is_valid BOOLEAN NOT NULL DEFAULT TRUE,
    valid_from DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to DATE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_sub_account UNIQUE (company_id, account_code, sub_account_code, valid_from)
);
```

### 3.4 departments（部門マスタ）

```sql
CREATE TABLE departments (
    department_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    department_code VARCHAR(20) NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    parent_department_id UUID REFERENCES departments(department_id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_company_dept_code UNIQUE (company_id, department_code)
);
```

### 3.5 projects（プロジェクトマスタ）

```sql
CREATE TABLE projects (
    project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    project_code VARCHAR(20) NOT NULL,
    project_name VARCHAR(200) NOT NULL,
    start_date DATE,
    end_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_company_project_code UNIQUE (company_id, project_code)
);
```

### 3.6 partners（取引先マスタ）

```sql
CREATE TABLE partners (
    partner_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    partner_code VARCHAR(20) NOT NULL,
    partner_name VARCHAR(255) NOT NULL,
    partner_name_kana VARCHAR(255),
    invoice_registration_number VARCHAR(14),
    partner_type VARCHAR(20) NOT NULL DEFAULT 'both', -- 'customer', 'supplier', 'both'
    bank_code VARCHAR(4),
    branch_code VARCHAR(3),
    account_no VARCHAR(7),
    account_name_kana VARCHAR(30),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_company_partner_code UNIQUE (company_id, partner_code)
);

CREATE INDEX idx_partners_invoice ON partners(invoice_registration_number);
```

---

## 4. 税・税率

### 4.1 tax_rules

```sql
CREATE TABLE tax_rules (
    tax_rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tax_type_code VARCHAR(20) NOT NULL, -- 'standard_10', 'reduced_8', 'non_taxable'
    tax_rate NUMERIC(4, 2) NOT NULL,    -- 0.10, 0.08, 0.00
    display_name VARCHAR(100) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tax_code_period UNIQUE (tax_type_code, valid_from)
);

CREATE INDEX idx_tax_rules_lookup ON tax_rules(tax_type_code, valid_from, valid_to);
```

### 4.2 tax_adjustment_rules

```sql
CREATE TABLE tax_adjustment_rules (
    rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    rule_name VARCHAR(100) NOT NULL,
    adjustment_type VARCHAR(20) NOT NULL, -- 'addition', 'subtraction'
    account_code VARCHAR(10) NOT NULL,
    allowable_limit_formula TEXT, -- 'min(8000000, actual * 0.50)'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## 5. 仕訳

### 5.1 journal_headers

```sql
CREATE TABLE journal_headers (
    journal_header_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    journal_no VARCHAR(50) NOT NULL,
    transaction_date DATE NOT NULL,
    posting_date DATE,
    slip_type VARCHAR(20) NOT NULL, -- 'transfer', 'receipt', 'payment'
    approval_status VARCHAR(20) NOT NULL DEFAULT 'draft', -- 'draft', 'waiting_approval', 'approved', 'posted', 'void'
    created_by UUID NOT NULL REFERENCES users(user_id),
    approved_by UUID REFERENCES users(user_id),
    approved_at TIMESTAMP WITH TIME ZONE,
    is_voided BOOLEAN NOT NULL DEFAULT FALSE,
    void_reason TEXT,
    source_type VARCHAR(50), -- 'manual', 'ai_suggestion', 'import', 'payroll', 'depreciation'
    source_reference_id UUID, -- AI推論ログやインポートログへの参照
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_company_journal_no UNIQUE (company_id, journal_no)
);

CREATE INDEX idx_journal_headers_lookup ON journal_headers(company_id, transaction_date, approval_status);
```

### 5.2 journal_lines

```sql
CREATE TABLE journal_lines (
    journal_line_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journal_header_id UUID NOT NULL REFERENCES journal_headers(journal_header_id) ON DELETE CASCADE,
    line_no INT NOT NULL,
    entry_type VARCHAR(10) NOT NULL, -- 'debit', 'credit'
    account_code VARCHAR(10) NOT NULL,
    sub_account_code VARCHAR(10),
    department_id UUID,
    project_id UUID,
    partner_id UUID REFERENCES partners(partner_id),
    tax_type_code VARCHAR(10) NOT NULL, -- 'tax_10_in', 'tax_10_ex', 'tax_8_in', 'non_taxable'
    invoice_category VARCHAR(20) NOT NULL DEFAULT 'qualified', -- 'qualified', 'transitional_80', 'transitional_50', 'unqualified'
    amount_excluding_tax NUMERIC(15, 4) NOT NULL,
    tax_amount NUMERIC(15, 4) NOT NULL,
    amount_including_tax NUMERIC(15, 4) NOT NULL,
    summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_journal_lines_header ON journal_lines(journal_header_id);
CREATE INDEX idx_journal_lines_account ON journal_lines(account_code, sub_account_code);
```

### 5.3 monthly_balances（月次集計キャッシュ）

```sql
CREATE TABLE monthly_balances (
    monthly_balance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    fiscal_year INT NOT NULL,
    fiscal_month INT NOT NULL,
    account_code VARCHAR(10) NOT NULL,
    sub_account_code VARCHAR(10),
    department_id UUID,
    opening_balance NUMERIC(15, 4) NOT NULL DEFAULT 0,
    debit_total NUMERIC(15, 4) NOT NULL DEFAULT 0,
    credit_total NUMERIC(15, 4) NOT NULL DEFAULT 0,
    closing_balance NUMERIC(15, 4) NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_monthly_balance UNIQUE (company_id, fiscal_year, fiscal_month, account_code, sub_account_code, department_id)
);

CREATE INDEX idx_monthly_balances_lookup ON monthly_balances(company_id, fiscal_year, fiscal_month);
```

---

## 6. AI推論

### 6.1 ai_inference_logs

```sql
CREATE TABLE ai_inference_logs (
    inference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    company_id UUID NOT NULL,
    source_type VARCHAR(50) NOT NULL, -- 'invoice_pdf', 'bank_csv', 'credit_card'
    source_file_id UUID,
    raw_payload JSONB,
    suggested_journal JSONB NOT NULL,
    confidence_score NUMERIC(5, 2) NOT NULL, -- 0.00 ~ 100.00
    applied_status VARCHAR(20) NOT NULL, -- 'pending_review', 'applied', 'rejected', 'modified'
    modified_diff JSONB,
    inference_engine_version VARCHAR(50) NOT NULL,
    model_name VARCHAR(100),
    model_version VARCHAR(50),
    inference_reason TEXT, -- AI説明責任：推論理由
    inference_duration_ms INT, -- 推論時間（ミリ秒）
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_inference_company ON ai_inference_logs(company_id, created_at DESC);
CREATE INDEX idx_ai_inference_status ON ai_inference_logs(applied_status);
```

---

## 7. 電帳法アーカイブ

### 7.1 archived_documents

```sql
CREATE TABLE archived_documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    file_path VARCHAR(512) NOT NULL,
    file_extension VARCHAR(10) NOT NULL,
    file_hash CHAR(64) NOT NULL, -- SHA-256
    file_size BIGINT NOT NULL,
    transaction_date DATE NOT NULL,
    transaction_amount NUMERIC(15, 2) NOT NULL,
    counterparty_name VARCHAR(255) NOT NULL,
    document_type VARCHAR(50) NOT NULL, -- 'invoice', 'receipt', 'contract'
    timestamp_token TEXT,
    timestamp_verified_at TIMESTAMP WITH TIME ZONE,
    journal_header_id UUID REFERENCES journal_headers(journal_header_id),
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_doc_search_requirements ON archived_documents(
    company_id, transaction_date, transaction_amount, counterparty_name
);
```

---

## 8. 承認ワークフロー

### 8.1 approval_policies

```sql
CREATE TABLE approval_policies (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    document_type VARCHAR(50) NOT NULL, -- 'payment_request', 'expense', 'journal'
    min_amount NUMERIC(15, 2) NOT NULL,
    max_amount NUMERIC(15, 2), -- NULL = 無限
    approver_role_id UUID NOT NULL REFERENCES roles(role_id),
    step_number INT NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_approval_policies_lookup ON approval_policies(company_id, document_type, is_active);
```

### 8.2 approval_requests（承認依頼）

```sql
CREATE TABLE approval_requests (
    request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    document_type VARCHAR(50) NOT NULL,
    document_id UUID NOT NULL, -- 仕訳ヘッダIDや支払申請ID
    requester_id UUID NOT NULL REFERENCES users(user_id),
    current_step INT NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'withdrawn'
    approved_by UUID REFERENCES users(user_id),
    approved_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_approval_pending ON approval_requests(company_id, status, current_step);
```

---

## 9. 支払・銀行

### 9.1 bank_accounts

```sql
CREATE TABLE bank_accounts (
    bank_account_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    bank_code VARCHAR(4) NOT NULL,
    branch_code VARCHAR(3) NOT NULL,
    account_type VARCHAR(10) NOT NULL, -- 'ordinary', 'current', 'savings'
    account_no_encrypted BYTEA NOT NULL, -- 暗号化保管
    account_name VARCHAR(100) NOT NULL,
    account_name_kana VARCHAR(40) NOT NULL,
    currency_code VARCHAR(3) NOT NULL DEFAULT 'JPY',
    valid_from DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to DATE,
    auto_fetch_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 9.2 bank_statement_details

```sql
CREATE TABLE bank_statement_details (
    statement_detail_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    bank_account_id UUID NOT NULL REFERENCES bank_accounts(bank_account_id),
    value_date DATE NOT NULL,
    withdraw_amount NUMERIC(15, 2) DEFAULT 0,
    deposit_amount NUMERIC(15, 2) DEFAULT 0,
    sender_name_kana VARCHAR(150) NOT NULL,
    description TEXT,
    is_reconciled BOOLEAN NOT NULL DEFAULT FALSE,
    reconciled_journal_header_id UUID REFERENCES journal_headers(journal_header_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_bank_unreconciled ON bank_statement_details(company_id, is_reconciled);
```

### 9.3 payment_requests（支払申請）

```sql
CREATE TABLE payment_requests (
    payment_request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    partner_id UUID REFERENCES partners(partner_id),
    payment_date DATE NOT NULL,
    payment_amount NUMERIC(15, 2) NOT NULL,
    bank_account_id UUID REFERENCES bank_accounts(bank_account_id),
    dest_bank_code VARCHAR(4),
    dest_branch_code VARCHAR(3),
    dest_account_type VARCHAR(10),
    dest_account_no VARCHAR(7),
    dest_account_name_kana VARCHAR(30),
    status VARCHAR(20) NOT NULL DEFAULT 'draft', -- 'draft', 'pending_approval', 'approved', 'executed', 'failed'
    journal_header_id UUID REFERENCES journal_headers(journal_header_id),
    zengin_export_batch_id UUID,
    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_payment_requests_status ON payment_requests(company_id, status, payment_date);
```

---

## 10. 固定資産

### 10.1 fixed_assets

```sql
CREATE TABLE fixed_assets (
    asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    asset_code VARCHAR(50) NOT NULL,
    asset_name VARCHAR(255) NOT NULL,
    acquisition_date DATE NOT NULL,
    acquisition_cost NUMERIC(15, 2) NOT NULL,
    depreciation_method VARCHAR(20) NOT NULL, -- 'straight_line', 'declining_balance', 'double_declining'
    useful_life INT NOT NULL, -- 耐用年数
    salvage_value NUMERIC(15, 2) DEFAULT 0,
    accumulated_depreciation NUMERIC(15, 2) DEFAULT 0,
    current_year_depreciation NUMERIC(15, 2) DEFAULT 0,
    department_id UUID REFERENCES departments(department_id),
    status VARCHAR(20) NOT NULL DEFAULT 'active', -- 'active', 'retired', 'sold'
    retired_date DATE,
    retire_reason TEXT,
    journal_header_id UUID REFERENCES journal_headers(journal_header_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_company_asset_code UNIQUE (company_id, asset_code)
);
```

---

## 11. 給与

### 11.1 employees

```sql
CREATE TABLE employees (
    employee_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    employee_code VARCHAR(20) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name_kana VARCHAR(50) NOT NULL,
    first_name_kana VARCHAR(50) NOT NULL,
    birth_date DATE NOT NULL,
    gender VARCHAR(10) NOT NULL, -- 'male', 'female'
    my_number_encrypted BYTEA, -- 暗号化保管
    health_insurance_no VARCHAR(20),
    pension_no VARCHAR(20),
    hire_date DATE NOT NULL,
    retire_date DATE,
    department_id UUID REFERENCES departments(department_id),
    monthly_salary NUMERIC(15, 2) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_company_emp_code UNIQUE (company_id, employee_code)
);
```

### 11.2 payroll_records（給与計算結果）

```sql
CREATE TABLE payroll_records (
    payroll_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    employee_id UUID NOT NULL REFERENCES employees(employee_id),
    target_year INT NOT NULL,
    target_month INT NOT NULL,
    base_salary NUMERIC(15, 2) NOT NULL DEFAULT 0,
    overtime_pay NUMERIC(15, 2) NOT NULL DEFAULT 0,
    allowance_total NUMERIC(15, 2) NOT NULL DEFAULT 0,
    deduction_health_insurance NUMERIC(15, 2) NOT NULL DEFAULT 0,
    deduction_pension NUMERIC(15, 2) NOT NULL DEFAULT 0,
    deduction_employment_insurance NUMERIC(15, 2) NOT NULL DEFAULT 0,
    deduction_income_tax NUMERIC(15, 2) NOT NULL DEFAULT 0,
    deduction_resident_tax NUMERIC(15, 2) NOT NULL DEFAULT 0,
    deduction_total NUMERIC(15, 2) NOT NULL DEFAULT 0,
    net_pay NUMERIC(15, 2) NOT NULL DEFAULT 0,
    journal_header_id UUID REFERENCES journal_headers(journal_header_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_payroll_emp_month UNIQUE (company_id, employee_id, target_year, target_month)
);
```

---

## 12. 事務タスク

### 12.1 office_tasks

```sql
CREATE TABLE office_tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    task_type VARCHAR(50) NOT NULL, -- 'employee_onboarding', 'expense_claim', 'insurance_qualify'
    related_employee_id UUID REFERENCES employees(employee_id),
    related_document_id UUID REFERENCES archived_documents(document_id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending', 'in_progress', 'completed', 'cancelled'
    assigned_to UUID REFERENCES users(user_id),
    meta_data JSONB,
    due_date DATE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_office_tasks_status ON office_tasks(company_id, status, due_date);
```

---

## 13. 監査・検知

### 13.1 audit_detection_logs

```sql
CREATE TABLE audit_detection_logs (
    detection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(company_id),
    journal_header_id UUID NOT NULL REFERENCES journal_headers(journal_header_id),
    risk_level VARCHAR(20) NOT NULL, -- 'critical', 'warning', 'info'
    detection_category VARCHAR(50) NOT NULL, -- 'duplicate', 'irregular_time', 'circular_transaction'
    reason_description TEXT NOT NULL,
    reviewer_user_id UUID REFERENCES users(user_id),
    review_status VARCHAR(20) DEFAULT 'unreviewed', -- 'unreviewed', 'confirmed_ok', 'needs_correction'
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_unreviewed ON audit_detection_logs(company_id, review_status);
```

---

## 14. セキュリティ

### 14.1 tenant_security_policies

```sql
CREATE TABLE tenant_security_policies (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL UNIQUE REFERENCES tenants(tenant_id),
    auth_type VARCHAR(20) NOT NULL DEFAULT 'password', -- 'password', 'saml', 'oidc'
    sso_issuer_url VARCHAR(512),
    sso_client_id VARCHAR(255),
    sso_client_secret_encrypted BYTEA,
    mfa_required BOOLEAN NOT NULL DEFAULT FALSE,
    allowed_ip_ranges TEXT[], -- CIDR配列
    session_timeout_minutes INT NOT NULL DEFAULT 60,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tenant_security ON tenant_security_policies(tenant_id);
```

---

## 15. API冪等性

### 15.1 idempotency_keys

```sql
CREATE TABLE idempotency_keys (
    key_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key VARCHAR(255) NOT NULL,
    tenant_id UUID NOT NULL,
    request_path VARCHAR(255) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'processing', -- 'processing', 'completed', 'failed'
    response_status INT,
    response_body TEXT,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tenant_idempotency_key UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX idx_idempotency_lookup ON idempotency_keys(tenant_id, idempotency_key);
```

---

## 16. Webhook

### 16.1 webhook_endpoints

```sql
CREATE TABLE webhook_endpoints (
    endpoint_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    target_url VARCHAR(512) NOT NULL,
    secret_token VARCHAR(255) NOT NULL,
    subscribed_events TEXT[] NOT NULL, -- '{"journal.posted", "payroll.closed"}'
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 16.2 webhook_deliveries

```sql
CREATE TABLE webhook_deliveries (
    delivery_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id UUID NOT NULL REFERENCES webhook_endpoints(endpoint_id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending', 'sending', 'succeeded', 'failed_retry', 'dead'
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_response_status INT,
    last_response_body TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_webhooks_queue ON webhook_deliveries(status, next_attempt_at);
```

---

## 17. ライセンス

### 17.1 licenses

```sql
CREATE TABLE licenses (
    license_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    license_type VARCHAR(20) NOT NULL, -- 'standard', 'enterprise', 'trial'
    max_users INT,
    max_companies INT,
    max_ai_inferences_per_month INT,
    max_api_calls_per_month INT,
    max_storage_gb INT,
    allowed_modules TEXT[], -- 有効モジュールリスト
    valid_from DATE NOT NULL,
    valid_to DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_licenses_tenant ON licenses(tenant_id, is_active);
```

### 17.2 usage_counters（利用量カウンタ）

```sql
CREATE TABLE usage_counters (
    counter_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    counter_type VARCHAR(30) NOT NULL, -- 'ai_inference', 'api_call', 'storage'
    counter_period VARCHAR(10) NOT NULL, -- '2026-06' etc.
    count_value BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_usage_counter UNIQUE (tenant_id, counter_type, counter_period)
);
```

---

## 18. インデックス設計方針

| 用途 | インデックス戦略 |
|------|----------------|
| 仕訳検索 | `(company_id, transaction_date, approval_status)` 複合 |
| 明細検索 | `(account_code, sub_account_code)` + `(journal_header_id)` |
| 電帳法3軸検索 | `(company_id, transaction_date, transaction_amount, counterparty_name)` 複合 |
| 未消込明細 | `(company_id, is_reconciled)` 部分インデックス |
| 承認待ち | `(company_id, status, current_step)` |
| Webhook配信 | `(status, next_attempt_at)` |

---

## 19. Row Level Security (RLS) ポリシー

全テーブルにテナント分離のためのRLSを適用する。

```sql
-- 例: journal_headers のRLSポリシー
ALTER TABLE journal_headers ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_journal_headers ON journal_headers
    USING (company_id IN (
        SELECT company_id FROM companies
        WHERE tenant_id = current_setting('app.tenant_id')::uuid
    ));
```

> アプリケーション接続時に `SET app.tenant_id = '...'` を実行し、
> テナント間のデータ漏洩をDBレベルで防ぐ。

---

## 20. テーブル作成順序（依存関係順）

```
1.  tenants
2.  users, roles, tenant_security_policies
3.  companies
4.  accounts, sub_accounts, departments, projects, partners
5.  tax_rules, tax_adjustment_rules
6.  user_roles, audit_trails
7.  journal_headers, journal_lines
8.  monthly_balances
9.  ai_inference_logs
10. archived_documents
11. approval_policies, approval_requests
12. bank_accounts, bank_statement_details, payment_requests
13. fixed_assets
14. employees, payroll_records
15. office_tasks
16. audit_detection_logs
17. idempotency_keys
18. webhook_endpoints, webhook_deliveries
19. licenses, usage_counters
```
