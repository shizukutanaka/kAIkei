# kAIkei — データ取り込み方式選択機能仕様書

> 本ドキュメントは既存会計ソフト・給与ソフトからのデータ取り込みについて、
> ソフトごとに「自動連携（API）」または「手動取り込み（CSV）」を選択可能にする機能を定義する。

---

## 1. 機能概要

### 1.1 目的

- 移行元ソフトによってAPIが利用可能なものとCSVエクスポートのみのものが混在する。
- ユーザーが各ソフトごとに取り込み方式を柔軟に選択できるようにする。
- 一度きりの移行だけでなく、継続的なデータ同期（API連携）にも対応する。

### 1.2 取り込み方式定義

| 方式 | 説明 | 必要な認証情報 | 実行タイミング |
|------|------|--------------|--------------|
| 自動連携（API） | 相手ソフトのAPIを直接呼び出してデータを取得 | APIキー/OAuth/Basic認証 | 定期実行 or 手動トリガー |
| 手動取り込み（CSV） | ユーザーがCSVファイルをエクスポートしてアップロード | 不要 | ユーザー手動操作 |
| 自動連携（スクレイピング） | Web画面からスクレイピングでデータ取得（非推奨） | ログインID/パスワード | 定期実行 |

---

## 2. 対象ソフトウェア一覧

### 2.1 会計ソフト

| ソフト名 | 自動連携（API） | 手動取り込み（CSV） | 備考 |
|---------|:---:|:---:|------|
| freee会計 | ✅ | ✅ | OAuth 2.0認証・REST API |
| マネーフォワード クラウド会計 | ✅ | ✅ | OAuth 2.0認証・REST API |
| 弥生会計 | ✅ | ✅ | 弥生API（一部プランのみ対応） |
| 弥生会計（API非対応プラン） | ❌ | ✅ | CSVエクスポートのみ |
| Dreamvison | ❌ | ✅ | CSV専用 |
| SAP Concur | ✅ | ✅ | OAuth 2.0・REST API（経費精算中心） |
| Oracle NetSuite | ✅ | ✅ | OAuth 2.0・SuiteTalk API |
| Zoho Books | ✅ | ✅ | OAuth 2.0・REST API |
| 汎用CSV | ❌ | ✅ | ユーザー定義マッピング |

### 2.2 給与ソフト

| ソフト名 | 自動連携（API） | 手動取り込み（CSV） | 備考 |
|---------|:---:|:---:|------|
| freee人事労務 | ✅ | ✅ | OAuth 2.0認証・REST API |
| マネーフォワード クラウド人事労務 | ✅ | ✅ | OAuth 2.0認証・REST API |
| 弥生給与 | ❌ | ✅ | CSVエクスポートのみ |
| SmartHR | ✅ | ✅ | APIトークン認証 |
| jinjer 給与 | ❌ | ✅ | CSVエクスポートのみ |
| 人事労務自由帳 | ❌ | ✅ | CSVエクスポートのみ |
| 汎用CSV（給与） | ❌ | ✅ | ユーザー定義マッピング |

### 2.3 銀行・金融機関

| 機関名 | 自動連携（API） | 手動取り込み（CSV） | 備考 |
|---------|:---:|:---:|------|
| 三菱UFJ銀行 | ✅ | ✅ | Mizuho API・全銀協API |
| 三井住友銀行 | ✅ | ✅ | SMBC API |
| みずほ銀行 | ✅ | ✅ | みずはAPI |
| りそな銀行 | ✅ | ✅ | りそなAPI |
| 地方銀行（全銀協API対応） | ✅ | ✅ | 全銀協標準API |
| 地方銀行（API非対応） | ❌ | ✅ | Web画面からCSV DL |
| ゆうちょ銀行 | ❌ | ✅ | CSV DLのみ |

---

## 3. データベース設計

### 3.1 外部連携設定テーブル

```sql
CREATE TABLE external_integration_configs (
    config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    company_id UUID NOT NULL REFERENCES companies(company_id),

    -- 連携先ソフトウェア情報
    software_category VARCHAR(20) NOT NULL,  -- 'accounting', 'payroll', 'bank'
    software_name VARCHAR(100) NOT NULL,     -- 'freee', 'yayoi', 'mf', etc.

    -- 取り込み方式
    import_mode VARCHAR(20) NOT NULL,        -- 'auto_api', 'manual_csv', 'auto_scrape'
    is_auto_import_enabled BOOLEAN NOT NULL DEFAULT FALSE,

    -- API認証情報（暗号化保存）
    api_endpoint TEXT,
    api_key_encrypted BYTEA,                 -- AES-256で暗号化
    oauth_client_id TEXT,
    oauth_client_secret_encrypted BYTEA,
    oauth_refresh_token_encrypted BYTEA,
    oauth_token_expires_at TIMESTAMP WITH TIME ZONE,
    basic_auth_username TEXT,
    basic_auth_password_encrypted BYTEA,

    -- スクレイピング設定
    scrape_login_url TEXT,
    scrape_username_encrypted BYTEA,
    scrape_password_encrypted BYTEA,

    -- 定期実行設定
    sync_frequency VARCHAR(20),              -- 'daily', 'weekly', 'monthly', 'on_demand'
    sync_day_of_week INT,                    -- 0=日, 1=月, ... 6=土（weekly時）
    sync_day_of_month INT,                   -- 1-31（monthly時）
    sync_time TIME,                          -- 実行時刻
    last_synced_at TIMESTAMP WITH TIME ZONE,
    last_sync_status VARCHAR(20),            -- 'success', 'failed', 'partial'
    last_sync_error_message TEXT,

    -- 取り込み対象データ
    import_targets JSONB NOT NULL DEFAULT '[]',  -- ['journals', 'masters', 'documents', 'payroll']

    -- マッピング設定
    account_mapping JSONB,                   -- 科目マッピング表
    tax_mapping JSONB,                       -- 税区分マッピング表
    department_mapping JSONB,                -- 部門マッピング表
    custom_field_mapping JSONB,              -- カスタムフィールドマッピング

    -- 状態
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,

    created_by UUID NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_import_mode CHECK (
        import_mode IN ('auto_api', 'manual_csv', 'auto_scrape')
    ),
    CONSTRAINT chk_software_category CHECK (
        software_category IN ('accounting', 'payroll', 'bank')
    )
);

CREATE INDEX idx_integration_tenant_company
    ON external_integration_configs(tenant_id, company_id);
CREATE INDEX idx_integration_active
    ON external_integration_configs(tenant_id, company_id, is_active, is_deleted);
```

### 3.2 取り込み実行履歴テーブル

```sql
CREATE TABLE import_execution_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_id UUID NOT NULL REFERENCES external_integration_configs(config_id),
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    company_id UUID NOT NULL REFERENCES companies(company_id),

    -- 実行情報
    import_mode VARCHAR(20) NOT NULL,        -- 'auto_api', 'manual_csv', 'auto_scrape'
    import_type VARCHAR(20) NOT NULL,        -- 'initial_migration', 'periodic_sync', 'manual_trigger'
    triggered_by UUID REFERENCES users(user_id),  -- 手動トリガー時のユーザー
    triggered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 実行結果
    status VARCHAR(20) NOT NULL,             -- 'running', 'success', 'failed', 'partial', 'cancelled'
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITH TIME ZONE,

    -- 取り込み件数
    total_records INT DEFAULT 0,
    success_records INT DEFAULT 0,
    failed_records INT DEFAULT 0,
    skipped_records INT DEFAULT 0,

    -- エラー情報
    error_summary TEXT,
    error_details JSONB,                     -- レコード別エラー詳細

    -- Dry-run情報
    is_dry_run BOOLEAN NOT NULL DEFAULT FALSE,
    dry_run_report_path TEXT,                -- S3パス

    -- アップロードファイル情報（CSV取り込み時）
    uploaded_file_name TEXT,
    uploaded_file_hash VARCHAR(64),

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_status CHECK (
        status IN ('running', 'success', 'failed', 'partial', 'cancelled')
    )
);

CREATE INDEX idx_import_logs_config
    ON import_execution_logs(config_id, triggered_at DESC);
CREATE INDEX idx_import_logs_tenant
    ON import_execution_logs(tenant_id, company_id, triggered_at DESC);
```

### 3.3 ソフトウェア対応マスタテーブル

```sql
CREATE TABLE supported_software (
    software_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    software_category VARCHAR(20) NOT NULL,  -- 'accounting', 'payroll', 'bank'
    software_code VARCHAR(50) NOT NULL UNIQUE,  -- 'freee_accounting', 'yayoi_accounting', etc.
    software_name VARCHAR(100) NOT NULL,
    software_name_ja VARCHAR(100) NOT NULL,

    -- 対応機能
    supports_auto_api BOOLEAN NOT NULL DEFAULT FALSE,
    supports_manual_csv BOOLEAN NOT NULL DEFAULT TRUE,
    supports_auto_scrape BOOLEAN NOT NULL DEFAULT FALSE,

    -- API仕様
    api_type VARCHAR(20),                    -- 'oauth2', 'api_key', 'basic_auth', 'none'
    api_base_url TEXT,
    api_docs_url TEXT,

    -- CSV仕様
    csv_format VARCHAR(50),                  -- 'yayoi_standard', 'freee_standard', 'mf_standard', 'generic'
    csv_template_url TEXT,
    csv_encoding VARCHAR(20) DEFAULT 'utf-8',

    -- 取り込み可能データ
    available_import_targets JSONB NOT NULL DEFAULT '[]',  -- ['journals', 'masters', 'documents', 'payroll']

    -- 表示順・状態
    display_order INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_software_category CHECK (
        software_category IN ('accounting', 'payroll', 'bank')
    )
);
```

---

## 4. API仕様

### 4.1 対応ソフト一覧取得

```
GET /api/v1/integrations/supported-software?category=accounting
```

**レスポンス 200:**

```json
{
  "items": [
    {
      "software_id": "uuid-...",
      "software_code": "freee_accounting",
      "software_name": "freee会計",
      "software_name_ja": "freee会計",
      "supports_auto_api": true,
      "supports_manual_csv": true,
      "supports_auto_scrape": false,
      "api_type": "oauth2",
      "csv_format": "freee_standard",
      "available_import_targets": ["journals", "masters", "documents"]
    },
    {
      "software_id": "uuid-...",
      "software_code": "yayoi_accounting",
      "software_name": "弥生会計",
      "software_name_ja": "弥生会計",
      "supports_auto_api": true,
      "supports_manual_csv": true,
      "supports_auto_scrape": false,
      "api_type": "oauth2",
      "csv_format": "yayoi_standard",
      "available_import_targets": ["journals", "masters"]
    },
    {
      "software_id": "uuid-...",
      "software_code": "dreamvison",
      "software_name": "Dreamvison",
      "software_name_ja": "Dreamvison",
      "supports_auto_api": false,
      "supports_manual_csv": true,
      "supports_auto_scrape": false,
      "api_type": "none",
      "csv_format": "generic",
      "available_import_targets": ["journals", "masters"]
    }
  ]
}
```

### 4.2 連携設定一覧取得

```
GET /api/v1/integrations/configs?company_id={company_id}
```

**レスポンス 200:**

```json
{
  "items": [
    {
      "config_id": "uuid-...",
      "software_category": "accounting",
      "software_name": "freee会計",
      "import_mode": "auto_api",
      "is_auto_import_enabled": true,
      "sync_frequency": "daily",
      "sync_time": "06:00",
      "last_synced_at": "2026-06-26T06:00:15+09:00",
      "last_sync_status": "success",
      "import_targets": ["journals", "masters"],
      "is_active": true
    },
    {
      "config_id": "uuid-...",
      "software_category": "payroll",
      "software_name": "弥生給与",
      "import_mode": "manual_csv",
      "is_auto_import_enabled": false,
      "import_targets": ["payroll"],
      "is_active": true
    }
  ]
}
```

### 4.3 連携設定作成

```
POST /api/v1/integrations/configs
```

**リクエストボディ:**

```json
{
  "company_id": "uuid-...",
  "software_category": "accounting",
  "software_code": "freee_accounting",
  "import_mode": "auto_api",
  "import_targets": ["journals", "masters", "documents"],

  "api_credentials": {
    "oauth_client_id": "xxx",
    "oauth_client_secret": "yyy"
  },

  "sync_frequency": "daily",
  "sync_time": "06:00",

  "account_mapping": {
    "1110": "1110",
    "1120": "1120",
    "4110": "4110"
  },
  "tax_mapping": {
    "1": "tax_10_ex",
    "2": "tax_8_ex",
    "3": "tax_10_in",
    "5": "non_taxable"
  }
}
```

**レスポンス 201:**

```json
{
  "config_id": "uuid-...",
  "software_name": "freee会計",
  "import_mode": "auto_api",
  "oauth_authorization_url": "https://api.freee.co.jp/oauth/authorize?client_id=xxx&redirect_uri=...",
  "status": "pending_authorization"
}
```

### 4.4 連携設定更新（取り込み方式切り替え）

```
PATCH /api/v1/integrations/configs/{config_id}
```

**リクエストボディ（自動→手動に切り替え）:**

```json
{
  "import_mode": "manual_csv",
  "is_auto_import_enabled": false
}
```

**レスポンス 200:**

```json
{
  "config_id": "uuid-...",
  "import_mode": "manual_csv",
  "is_auto_import_enabled": false,
  "updated_at": "2026-06-26T14:30:00+09:00"
}
```

### 4.5 手動CSVアップロード取り込み

```
POST /api/v1/integrations/configs/{config_id}/import-csv
```

**リクエスト:** `multipart/form-data`

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| file | File | ✅ | CSVファイル |
| dry_run | Boolean | — | `true`でシミュレーションのみ |
| import_target | String | ✅ | `journals` / `masters` / `payroll` |

**レスポンス 200（Dry-run）:**

```json
{
  "log_id": "uuid-...",
  "is_dry_run": true,
  "status": "success",
  "total_records": 1250,
  "success_records": 1230,
  "failed_records": 20,
  "skipped_records": 0,
  "errors": [
    {
      "row": 45,
      "error": "MIG-VAL-001: 科目コード '9999' がマッピング表に存在しません",
      "source_data": {"date": "2026/04/15", "amount": 50000, "account": "9999"}
    }
  ],
  "dry_run_report_path": "s3://bucket/reports/import/uuid-.../dry_run_report.csv"
}
```

**レスポンス 201（本番実行）:**

```json
{
  "log_id": "uuid-...",
  "is_dry_run": false,
  "status": "success",
  "total_records": 1230,
  "success_records": 1230,
  "failed_records": 0,
  "imported_journal_ids": ["uuid-...", "uuid-..."]
}
```

### 4.6 自動API連携の手動トリガー

```
POST /api/v1/integrations/configs/{config_id}/sync
```

**リクエストボディ:**

```json
{
  "dry_run": false,
  "date_from": "2026-06-01",
  "date_to": "2026-06-26"
}
```

**レスポンス 202:**

```json
{
  "log_id": "uuid-...",
  "status": "running",
  "message": "同期を開始しました。完了後にログで結果を確認できます。"
}
```

### 4.7 取り込み実行履歴取得

```
GET /api/v1/integrations/configs/{config_id}/logs?page=1&page_size=20
```

**レスポンス 200:**

```json
{
  "items": [
    {
      "log_id": "uuid-...",
      "import_mode": "auto_api",
      "import_type": "periodic_sync",
      "status": "success",
      "triggered_at": "2026-06-26T06:00:15+09:00",
      "finished_at": "2026-06-26T06:02:30+09:00",
      "total_records": 150,
      "success_records": 150,
      "failed_records": 0
    }
  ],
  "total": 45,
  "page": 1,
  "page_size": 20
}
```

### 4.8 OAuth認証コールバック

```
GET /api/v1/integrations/oauth/callback?code={code}&state={config_id}
```

**レスポンス 200:**

```json
{
  "config_id": "uuid-...",
  "status": "authorized",
  "message": "freee会計との連携が完了しました。"
}
```

---

## 5. 画面仕様

### 5.1 連携設定一覧画面

```
┌─────────────────────────────────────────────────────┐
│  外部連携設定                                        │
├─────────────────────────────────────────────────────┤
│  タブ: [会計ソフト(2)] [給与ソフト(1)] [銀行(3)]      │
├──┬──────────┬──────────┬──────────┬──────────┬──────┤
│  │ソフト名   │取り込み方式│同期頻度   │最終同期   │操作  │
├──┼──────────┼──────────┼──────────┼──────────┼──────┤
│  │freee会計  │自動(API)  │毎日6:00  │06/26 06:00│[編集]│
│  │           │           │          │成功       │[履歴]│
│  │弥生給与   │手動(CSV)  │—        │06/20 14:00│[編集]│
│  │           │           │          │成功       │[履歴]│
└──┴──────────┴──────────┴──────────┴──────────┴──────┘
  [+ 新規連携追加]
```

### 5.2 新規連携追加画面

```
┌─────────────────────────────────────────────────────┐
│  新規連携追加                                [×]      │
├─────────────────────────────────────────────────────┤
│  カテゴリ: [会計ソフト ▼]                             │
│                                                     │
│  ソフトウェア選択:                                    │
│  ┌─────────────────────────────────────────┐        │
│  │ ○ freee会計        [自動API] [CSV]       │        │
│  │ ○ マネーフォワード  [自動API] [CSV]       │        │
│  │ ○ 弥生会計          [自動API] [CSV]       │        │
│  │ ○ Dreamvison       [---  ] [CSV]        │        │
│  │ ○ 汎用CSV           [---  ] [CSV]        │        │
│  └─────────────────────────────────────────┘        │
│                                                     │
│  選択中: freee会計                                    │
│                                                     │
│  取り込み方式:                                        │
│  ◉ 自動連携（API）— 定期的に自動でデータを取得         │
│  ○ 手動取り込み（CSV）— CSVファイルをアップロード      │
│                                                     │
│  取り込みデータ:                                      │
│  ☑ 仕訳データ                                         │
│  ☑ マスタデータ（勘定科目・取引先等）                   │
│  ☐ 証憑ファイル                                       │
│                                                     │
│  [次へ]                                              │
└─────────────────────────────────────────────────────┘
```

### 5.3 API認証設定画面（自動連携選択時）

```
┌─────────────────────────────────────────────────────┐
│  API認証設定 — freee会計                      [×]      │
├─────────────────────────────────────────────────────┤
│  認証方式: OAuth 2.0                                  │
│                                                     │
│  1. freee開発者サイトでアプリケーションを登録し、       │
│     クライアントIDとシークレットを取得してください。     │
│     [freee開発者サイトを開く →]                       │
│                                                     │
│  クライアントID:                                   │
│  [                                          ]        │
│                                                     │
│  クライアントシークレット:                            │
│  [********                                  ]        │
│                                                     │
│  コールバックURL:                                    │
│  https://app.cotton-erp.com/api/v1/integrations/     │
│  oauth/callback                                      │
│  [コピー]                                            │
│                                                     │
│  2. 認証を開始します。                                │
│  [freeeにログインして認証 →]                          │
│                                                     │
│  同期設定:                                            │
│  同期頻度: [毎日 ▼]                                   │
│  実行時刻: [06:00 ▼]                                 │
│                                                     │
│  [保存して認証を開始]                                 │
└─────────────────────────────────────────────────────┘
```

### 5.4 CSV取り込み画面（手動取り込み選択時）

```
┌─────────────────────────────────────────────────────┐
│  CSV取り込み — 弥生給与                       [×]      │
├─────────────────────────────────────────────────────┤
│  取り込みデータ: [給与データ ▼]                        │
│                                                     │
│  ┌─────────────────────────────────────────┐        │
│  │                                         │        │
│  │    CSVファイルをドラッグ&ドロップ          │        │
│  │       または [ファイル選択]               │        │
│  │    文字コード: [UTF-8 ▼]                 │        │
│  │                                         │        │
│  └─────────────────────────────────────────┘        │
│                                                     │
│  ☐ Dry-run（シミュレーションのみ）                    │
│                                                     │
│  [取り込み実行]                                       │
│                                                     │
│  ── 結果 ──                                          │
│  総件数: 1,250  成功: 1,230  失敗: 20  スキップ: 0   │
│                                                     │
│  [エラー詳細をダウンロード]                           │
│  [成功データを確定]                                   │
└─────────────────────────────────────────────────────┘
```

### 5.5 連携設定編集画面（方式切り替え）

```
┌─────────────────────────────────────────────────────┐
│  連携設定編集 — freee会計                    [×]      │
├─────────────────────────────────────────────────────┤
│  ソフトウェア: freee会計                              │
│                                                     │
│  取り込み方式:                                        │
│  ◉ 自動連携（API）  [現在の設定]                      │
│     同期頻度: [毎日 ▼]  実行時刻: [06:00 ▼]           │
│     認証状態: ✅ 認証済み（トークン有効）              │
│     [手動同期実行]                                    │
│                                                     │
│  ○ 手動取り込み（CSV）                               │
│     CSVファイルをアップロードして取り込みます。         │
│     ※ 自動連携を停止し、手動運用に切り替えます。        │
│                                                     │
│  取り込みデータ:                                      │
│  ☑ 仕訳データ                                         │
│  ☑ マスタデータ                                       │
│  ☐ 証憑ファイル                                       │
│                                                     │
│  マッピング設定:                                      │
│  [科目マッピング編集 →]                               │
│  [税区分マッピング編集 →]                             │
│  [部門マッピング編集 →]                               │
│                                                     │
│  [保存]  [連携を解除]                                 │
└─────────────────────────────────────────────────────┘
```

### 5.6 取り込み実行履歴画面

```
┌─────────────────────────────────────────────────────┐
│  取り込み履歴 — freee会計                             │
├─────────────────────────────────────────────────────┤
│  期間: [2026/06/01]〜[2026/06/30]  [検索]             │
├──┬──────┬──────────┬──────────┬──────┬──────┬───────┤
│  │日時   │方式      │タイプ    │状態  │件数   │操作   │
├──┼──────┼──────────┼──────────┼──────┼──────┼───────┤
│  │06/26 │自動(API) │定期同期  │成功  │150件 │[詳細]│
│  │06:00 │          │          │      │      │      │
│  │06/25 │自動(API) │定期同期  │成功  │145件 │[詳細]│
│  │06:00 │          │          │      │      │      │
│  │06/24 │自動(API) │定期同期  │部分  │140件 │[詳細]│
│  │06:00 │          │          │失敗  │(5失敗)│      │
│  │06/20 │手動(CSV) │手動実行  │成功  │1250件│[詳細]│
│  │14:00 │          │          │      │      │      │
└──┴──────┴──────────┴──────────┴──────┴──────┴───────┘
  < 1 2 3 > (20件/ページ)
```

---

## 6. 自動連携（API）アダプタ仕様

### 6.1 アダプタパターン

各ソフトウェアのAPI差異を吸収するため、共通インターフェースを実装するアダプタパターンを採用する。

```python
class ImportAdapter(ABC):
    """外部ソフトウェアからのデータ取り込みアダプタの抽象基底クラス"""

    @abstractmethod
    async def authenticate(self, credentials: dict) -> bool:
        """認証を実行し、アクセストークンを取得する"""
        pass

    @abstractmethod
    async def fetch_journals(self, date_from: date, date_to: date) -> list[dict]:
        """指定期間の仕訳データを取得する"""
        pass

    @abstractmethod
    async def fetch_masters(self) -> dict:
        """マスタデータ（勘定科目・取引先等）を取得する"""
        pass

    @abstractmethod
    async def fetch_documents(self, date_from: date, date_to: date) -> list[dict]:
        """証憑ファイルを取得する"""
        pass

    @abstractmethod
    async def fetch_payroll(self, year: int, month: int) -> list[dict]:
        """給与データを取得する"""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """接続テストを実行する"""
        pass
```

### 6.2 実装アダプタ一覧

| アダプタ | 対象ソフト | APIタイプ | 取得可能データ |
|---------|-----------|----------|--------------|
| `FreeeAccountingAdapter` | freee会計 | OAuth 2.0 | 仕訳・マスタ・証憑 |
| `MfAccountingAdapter` | マネーフォワード クラウド会計 | OAuth 2.0 | 仕訳・マスタ |
| `YayoiAccountingAdapter` | 弥生会計 | OAuth 2.0 | 仕訳・マスタ |
| `FreeePayrollAdapter` | freee人事労務 | OAuth 2.0 | 給与・社員マスタ |
| `MfPayrollAdapter` | マネーフォワード クラウド人事労務 | OAuth 2.0 | 給与・社員マスタ |
| `SmartHrAdapter` | SmartHR | APIトークン | 社員マスタ・勤怠 |
| `BankApiAdapter` | 銀行API（全銀協標準） | OAuth 2.0 / Mutual TLS | 銀行明細 |
| `CsvImportAdapter` | 汎用CSV（全ソフト対応） | — | 仕訳・マスタ・給与（CSV内容依存） |

### 6.3 CSV汎用アダプタのカラムマッピング

CSV取り込み時はユーザーがカラムマッピングを定義可能：

```json
{
  "column_mapping": {
    "transaction_date": "取引日",
    "journal_number": "伝票番号",
    "debit_account_code": "借方科目コード",
    "debit_account_name": "借方科目名",
    "debit_sub_account": "借方補助科目",
    "debit_amount": "借方金額",
    "credit_account_code": "貸方科目コード",
    "credit_account_name": "貸方科目名",
    "credit_sub_account": "貸方補助科目",
    "credit_amount": "貸方金額",
    "summary": "摘要",
    "tax_category": "税区分",
    "department": "部門"
  },
  "date_format": "YYYY/MM/DD",
  "encoding": "utf-8",
  "delimiter": ",",
  "header_row": true,
  "skip_rows": 0
}
```

---

## 7. セキュリティ要件

### 7.1 認証情報の暗号化

| 項目 | 仕様 |
|------|------|
| 暗号化方式 | AES-256-GCM |
| 鍵管理 | AWS KMS / HashiCorp Vault |
| 暗号化対象 | APIキー・OAuthシークレット・OAuthリフレッシュトークン・Basic認証パスワード・スクレイピングパスワード |
| アクセス制御 | 認証情報の復号は連携実行時のみ・アプリ層でのみ実施 |

### 7.2 データ取り込み時のセキュリティ

| 項目 | 仕様 |
|------|------|
| 通信暗号化 | 全API呼出はHTTPS/TLS 1.2以上 |
| ファイル検証 | アップロードCSVのマルウェアスキャン（ClamAV等） |
| ファイルサイズ制限 | 最大50MB |
| ファイル形式制限 | `.csv` `.txt` のみ（実行ファイル除外） |
| 監査ログ | 全取り込み操作を `audit_trails` に記録 |
| マスキング | API経由で取得した個人情報（マイナンバー等）は即座に暗号化 |

---

## 8. エラーハンドリング

### 8.1 エラー分類

| エラーカテゴリ | 例 | 対応 |
|--------------|-----|------|
| 認証エラー | OAuthトークン期限切れ・APIキー無効 | リフレッシュトークンで再認証・失敗時はユーザーへ通知 |
| ネットワークエラー | タイムアウト・接続拒否 | 指数バックオフで3回再試行・失敗時はログ記録 |
| データ形式エラー | APIレスポンス形式変更・CSV形式不正 | エラー詳細をログに記録・ユーザーへ通知 |
| マッピングエラー | 科目コードがマッピング表に存在しない | 該当レコードをスキップ・エラーレポートに記録 |
| バリデーションエラー | 貸借不一致・金額ゼロ | 該当レコードをスキップ・エラーレポートに記録 |
| レート制限 | API呼出回数制限 | 待機後に再試行・制限緩和をユーザーへ通知 |

### 8.2 エラー通知

| 通知先 | タイミング | 方法 |
|--------|----------|------|
| 連携設定担当者 | 取り込み失敗時 | 画面通知 + Email |
| 管理者 | 連続3回失敗時 | Email + Slack |
| 運用チーム | システムエラー時 | Slack #alerts |

---

## 9. 定期同期スケジューラ仕様

### 9.1 実行フロー

```
[スケジューラ起動（毎時00分）]
  → 有効な自動連携設定を取得
    → (config where is_auto_import_enabled=TRUE AND is_active=TRUE)
      → [各設定ごとに]
        → 同期時刻到達判定
          → [到達?]
            ─No→ 次の設定へ
            ─Yes→ アダプタ取得 → 認証確認
              → [認証OK?]
                ─No→ リフレッシュトークンで再認証
                  → [成功?]
                    ─No→ エラーログ記録 → 通知 → 次へ
                    ─Yes→ 次へ
                ─Yes→ データ取得実行
                  → バリデーション・マッピング変換
                    → DBインサート
                      → 結果ログ記録
                        → [成功?]
                          ─Yes→ last_synced_at更新 → 終了
                          ─No→ エラーログ → 通知 → 終了
```

### 9.2 同期重複防止

| 仕様 | 説明 |
|------|------|
| 重複チェック | 同一config_idでstatus=runningのログが存在する場合は新規起動しない |
| ロック期間 | 最長30分（30分経過でタイムアウト強制終了） |
| 冪等性 | 同一期間のデータは再取り込み時に既存レコードをスキップ（外部IDで判定） |
