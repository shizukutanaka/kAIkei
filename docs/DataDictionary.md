# kAIkei — データ辞書（Data Dictionary）

> 本ドキュメントはkAIkeiの全テーブル・全カラム・業務用語を統一定義する。
> 画面・API・帳票・DB間の整合性を維持するための単一ソース・オブ・トゥルースである。

---

## 1. テナント・ユーザー・ロール

### 1.1 tenants

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| テナントID | tenant_id | UUID | ✅ PK | システム内一意識別子（自動生成） |
| テナント名 | tenant_name | VARCHAR(255) | ✅ | テナント（組織）の名称 |
| プラン種別 | plan_type | VARCHAR(20) | ✅ | `trial` / `standard` / `enterprise` |
| 有効フラグ | is_active | BOOLEAN | ✅ | アクティブテナントかどうか |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | レコード作成日時 |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | レコード最終更新日時 |

### 1.2 users

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| ユーザーID | user_id | UUID | ✅ PK | システム内一意識別子（自動生成） |
| テナントID | tenant_id | UUID | ✅ FK | 所属テナント |
| メールアドレス | email | VARCHAR(255) | ✅ | ログインID（テナント内一意） |
| パスワードハッシュ | password_hash | VARCHAR(255) | — | bcryptハッシュ（SSO利用時はNULL） |
| 表示名 | display_name | VARCHAR(100) | ✅ | ユーザーの表示名 |
| 有効フラグ | is_active | BOOLEAN | ✅ | アクティブユーザーかどうか |
| 最終ログイン日時 | last_login_at | TIMESTAMPTZ | — | 最後にログインした日時 |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | レコード作成日時 |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | レコード最終更新日時 |

### 1.3 roles

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| ロールID | role_id | UUID | ✅ PK | システム内一意識別子 |
| テナントID | tenant_id | UUID | ✅ FK | 所属テナント |
| ロール名 | role_name | VARCHAR(100) | ✅ | 表示名（例: 経理部長） |
| ロールコード | role_code | VARCHAR(50) | ✅ | システム識別子（例: `accounting_manager`） |
| 説明 | description | TEXT | — | ロールの説明 |
| システム標準フラグ | is_system_role | BOOLEAN | ✅ | システム標準ロール（削除不可）かどうか |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | レコード作成日時 |

### 1.4 user_roles

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| ユーザーID | user_id | UUID | ✅ PK/FK | ユーザー |
| ロールID | role_id | UUID | ✅ PK/FK | ロール |
| 会社ID | company_id | UUID | — FK | 適用範囲（NULL=全会社対象） |
| 割当日時 | assigned_at | TIMESTAMPTZ | ✅ | ロール割当日時 |

### 1.5 audit_trails

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 証跡ID | trail_id | UUID | ✅ PK | 一意識別子 |
| テナントID | tenant_id | UUID | ✅ | 所属テナント |
| ユーザーID | user_id | UUID | ✅ | 操作実行者 |
| 会社ID | company_id | UUID | — | 対象会社 |
| アクション | action | VARCHAR(50) | ✅ | `login`/`logout`/`create`/`update`/`delete`/`export`/`print`/`api_call`/`ai_approve` |
| リソース種別 | resource_type | VARCHAR(50) | — | `journal`/`document`/`payment`/`master` |
| リソースID | resource_id | UUID | — | 対象レコードのID |
| 詳細 | detail | JSONB | — | 変更前後のスナップショット等 |
| IPアドレス | ip_address | INET | — | 接続元IP |
| ユーザーエージェント | user_agent | TEXT | — | ブラウザ/クライアント情報 |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | 操作日時 |

---

## 2. 会社・マスタ

### 2.1 companies

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 会社ID | company_id | UUID | ✅ PK | システム内一意識別子 |
| テナントID | tenant_id | UUID | ✅ FK | 所属テナント |
| 法人番号 | corporate_number | CHAR(13) | — UNIQUE | 13桁の法人番号 |
| 適格請求書発行事業者番号 | invoice_registration_number | VARCHAR(14) | — | T+13桁 |
| 会社名 | company_name | VARCHAR(255) | ✅ | 正式名称 |
| 会社名カナ | company_name_kana | VARCHAR(255) | — | カナ名称 |
| 起算月 | fiscal_month_start | INT | ✅ | 会計年度の開始月（デフォルト: 4） |
| 課税方式 | tax_system_type | SMALLINT | ✅ | 1:本則課税, 2:簡易課税, 3:2割特例 |
| 有効フラグ | is_active | BOOLEAN | ✅ | アクティブ会社かどうか |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

### 2.2 accounts

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 勘定科目ID | account_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 勘定科目コード | account_code | VARCHAR(10) | ✅ | 科目コード（例: `100`, `812`） |
| 勘定科目名 | account_name | VARCHAR(100) | ✅ | 科目名称（例: 現金, 消耗品費） |
| 科目種別 | account_type | VARCHAR(20) | ✅ | `asset`/`liability`/`equity`/`revenue`/`expense` |
| 残高種別 | balance_type | VARCHAR(10) | ✅ | `debit`(借方残) / `credit`(貸方残) |
| 有効フラグ | is_valid | BOOLEAN | ✅ | 有効かどうか |
| 適用開始日 | valid_from | DATE | ✅ | この科目が有効になった日 |
| 適用終了日 | valid_to | DATE | — | この科目が無効になった日（NULL=現在有効） |
| 表示順 | display_order | INT | ✅ | 一覧表示のソート順 |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

### 2.3 sub_accounts

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 補助科目ID | sub_account_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 勘定科目コード | account_code | VARCHAR(10) | ✅ | 親科目コード |
| 補助科目コード | sub_account_code | VARCHAR(10) | ✅ | 補助科目コード |
| 補助科目名 | sub_account_name | VARCHAR(100) | ✅ | 補助科目名称 |
| 有効フラグ | is_valid | BOOLEAN | ✅ | 有効かどうか |
| 適用開始日 | valid_from | DATE | ✅ | — |
| 適用終了日 | valid_to | DATE | — | — |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

### 2.4 departments

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 部門ID | department_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 部門コード | department_code | VARCHAR(20) | ✅ | 部門コード |
| 部門名 | department_name | VARCHAR(100) | ✅ | 部門名称 |
| 親部門ID | parent_department_id | UUID | — FK | 階層構造の親部門 |
| 有効フラグ | is_active | BOOLEAN | ✅ | — |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

### 2.5 projects

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| プロジェクトID | project_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| プロジェクトコード | project_code | VARCHAR(20) | ✅ | プロジェクトコード |
| プロジェクト名 | project_name | VARCHAR(200) | ✅ | プロジェクト名称 |
| 開始日 | start_date | DATE | — | — |
| 終了日 | end_date | DATE | — | — |
| 有効フラグ | is_active | BOOLEAN | ✅ | — |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

### 2.6 partners

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 取引先ID | partner_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 取引先コード | partner_code | VARCHAR(20) | ✅ | 取引先コード |
| 取引先名 | partner_name | VARCHAR(255) | ✅ | 正式名称 |
| 取引先名カナ | partner_name_kana | VARCHAR(255) | — | カナ名称（消込マッチング用） |
| 適格請求書番号 | invoice_registration_number | VARCHAR(14) | — | T+13桁 |
| 取引先種別 | partner_type | VARCHAR(20) | ✅ | `customer`/`supplier`/`both` |
| 銀行コード | bank_code | VARCHAR(4) | — | 振込先金融機関コード |
| 支店コード | branch_code | VARCHAR(3) | — | 振込先支店コード |
| 口座番号 | account_no | VARCHAR(7) | — | 振込先口座番号 |
| 口座名義カナ | account_name_kana | VARCHAR(30) | — | 振込先口座名義（半角カナ） |
| 有効フラグ | is_active | BOOLEAN | ✅ | — |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

---

## 3. 税・税率

### 3.1 tax_rules

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 税ルールID | tax_rule_id | UUID | ✅ PK | 一意識別子 |
| 税区分コード | tax_type_code | VARCHAR(20) | ✅ | `standard_10`/`reduced_8`/`non_taxable` |
| 税率 | tax_rate | NUMERIC(4,2) | ✅ | 0.10 / 0.08 / 0.00 |
| 表示名 | display_name | VARCHAR(100) | ✅ | 「課税10%」「軽減8%」等 |
| 適用開始日 | valid_from | DATE | ✅ | この税率の適用開始日 |
| 適用終了日 | valid_to | DATE | — | この税率の適用終了日 |
| 有効フラグ | is_active | BOOLEAN | ✅ | — |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |

### 3.2 tax_adjustment_rules

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| ルールID | rule_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| ルール名 | rule_name | VARCHAR(100) | ✅ | 「交際費不算入」「減価償却超過」等 |
| 調整種別 | adjustment_type | VARCHAR(20) | ✅ | `addition`(加算) / `subtraction`(減算) |
| 勘定科目コード | account_code | VARCHAR(10) | ✅ | 対象科目 |
| 限度額計算式 | allowable_limit_formula | TEXT | — | 「min(8000000, actual * 0.50)」等 |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |

---

## 4. 仕訳

### 4.1 journal_headers

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 仕訳ヘッダID | journal_header_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 仕訳番号 | journal_no | VARCHAR(50) | ✅ | 年度内で一意の採番（例: `JRN-2026000001`） |
| 取引日 | transaction_date | DATE | ✅ | 取引発生日 |
| 帳簿反映日 | posting_date | DATE | — | 帳簿に反映された日 |
| 伝票種別 | slip_type | VARCHAR(20) | ✅ | `transfer`(振替) / `receipt`(入金) / `payment`(出金) |
| 承認状態 | approval_status | VARCHAR(20) | ✅ | `draft`/`waiting_approval`/`approved`/`posted`/`void` |
| 起票者ID | created_by | UUID | ✅ FK | 作成ユーザー |
| 承認者ID | approved_by | UUID | — FK | 承認ユーザー |
| 承認日時 | approved_at | TIMESTAMPTZ | — | 承認実行日時 |
| 無効フラグ | is_voided | BOOLEAN | ✅ | 無効化（逆仕訳）済みかどうか |
| 無効理由 | void_reason | TEXT | — | 無効化の理由 |
| 登録元種別 | source_type | VARCHAR(50) | — | `manual`/`ai_suggestion`/`import`/`payroll`/`depreciation` |
| 登録元参照ID | source_reference_id | UUID | — | AI推論ログやインポートログへの参照 |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

### 4.2 journal_lines

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 仕訳明細ID | journal_line_id | UUID | ✅ PK | 一意識別子 |
| 仕訳ヘッダID | journal_header_id | UUID | ✅ FK | 親仕訳（CASCADE削除） |
| 明細行番号 | line_no | INT | ✅ | 明細行番号（1, 2, 3...） |
| 貸借区分 | entry_type | VARCHAR(10) | ✅ | `debit`(借方) / `credit`(貸方) |
| 勘定科目コード | account_code | VARCHAR(10) | ✅ | 勘定科目コード |
| 補助科目コード | sub_account_code | VARCHAR(10) | — | 補助科目コード |
| 部門ID | department_id | UUID | — | 部門 |
| プロジェクトID | project_id | UUID | — | プロジェクト |
| 取引先ID | partner_id | UUID | — FK | 取引先 |
| 税区分コード | tax_type_code | VARCHAR(10) | ✅ | `tax_10_in`/`tax_10_ex`/`tax_8_in`/`non_taxable` |
| インボイス区分 | invoice_category | VARCHAR(20) | ✅ | `qualified`/`transitional_80`/`transitional_50`/`unqualified` |
| 税抜金額 | amount_excluding_tax | NUMERIC(15,4) | ✅ | 税抜金額 |
| 消費税額 | tax_amount | NUMERIC(15,4) | ✅ | 消費税額 |
| 税込金額 | amount_including_tax | NUMERIC(15,4) | ✅ | 税込金額 |
| 摘要 | summary | TEXT | — | 摘要テキスト |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

### 4.3 monthly_balances

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 月次残高ID | monthly_balance_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 会計年度 | fiscal_year | INT | ✅ | 年度（例: 2026） |
| 会計月 | fiscal_month | INT | ✅ | 月（1〜12） |
| 勘定科目コード | account_code | VARCHAR(10) | ✅ | 科目 |
| 補助科目コード | sub_account_code | VARCHAR(10) | — | 補助科目 |
| 部門ID | department_id | UUID | — | 部門 |
| 期首残高 | opening_balance | NUMERIC(15,4) | ✅ | 月初残高 |
| 借方合計 | debit_total | NUMERIC(15,4) | ✅ | 当月借方合計 |
| 貸方合計 | credit_total | NUMERIC(15,4) | ✅ | 当月貸方合計 |
| 期末残高 | closing_balance | NUMERIC(15,4) | ✅ | 月末残高 |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

---

## 5. AI推論

### 5.1 ai_inference_logs

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 推論ID | inference_id | UUID | ✅ PK | 一意識別子 |
| テナントID | tenant_id | UUID | ✅ | 所属テナント |
| 会社ID | company_id | UUID | ✅ | 所属会社 |
| 入力元種別 | source_type | VARCHAR(50) | ✅ | `invoice_pdf`/`bank_csv`/`credit_card` |
| 入力ファイルID | source_file_id | UUID | — | オブジェクトストレージ上の証憑ファイルID |
| 元データ | raw_payload | JSONB | — | 推論前の解析元テキスト・OCRデータ |
| 提案仕訳 | suggested_journal | JSONB | ✅ | AIが提案した仕訳構造 |
| 信頼度スコア | confidence_score | NUMERIC(5,2) | ✅ | 0.00〜100.00 |
| 適用状態 | applied_status | VARCHAR(20) | ✅ | `pending_review`/`applied`/`rejected`/`modified` |
| 修正差分 | modified_diff | JSONB | — | ユーザーが修正した箇所の差分 |
| 推論エンジンバージョン | inference_engine_version | VARCHAR(50) | ✅ | エンジンのバージョン |
| モデル名 | model_name | VARCHAR(100) | — | AIモデル名 |
| モデルバージョン | model_version | VARCHAR(50) | — | AIモデルバージョン |
| 推論理由 | inference_reason | TEXT | — | AI説明責任：推論理由テキスト |
| 推論時間 | inference_duration_ms | INT | — | 推論にかかった時間（ミリ秒） |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | 推論実行日時 |

---

## 6. 電帳法アーカイブ

### 6.1 archived_documents

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| ドキュメントID | document_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| ファイルパス | file_path | VARCHAR(512) | ✅ | オブジェクトストレージ上の格納パス |
| ファイル拡張子 | file_extension | VARCHAR(10) | ✅ | `pdf`/`jpeg`/`png`等 |
| ファイルハッシュ | file_hash | CHAR(64) | ✅ | SHA-256ハッシュ値（改ざん検知用） |
| ファイルサイズ | file_size | BIGINT | ✅ | バイト数 |
| 取引年月日 | transaction_date | DATE | ✅ | 電帳法検索要件① |
| 取引金額 | transaction_amount | NUMERIC(15,2) | ✅ | 電帳法検索要件② |
| 取引先名称 | counterparty_name | VARCHAR(255) | ✅ | 電帳法検索要件③ |
| ドキュメント種別 | document_type | VARCHAR(50) | ✅ | `invoice`/`receipt`/`contract`/`other` |
| タイムスタンプトークン | timestamp_token | TEXT | — | 外部タイムスタンプ局のトークン |
| タイムスタンプ検証日時 | timestamp_verified_at | TIMESTAMPTZ | — | 検証実行日時 |
| 紐付け仕訳ID | journal_header_id | UUID | — FK | 関連する仕訳ヘッダ |
| 作成者ID | created_by | UUID | ✅ FK | アップロード実行者 |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | アーカイブ日時 |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |
| 削除フラグ | is_deleted | BOOLEAN | ✅ | 論理削除フラグ（物理削除は禁止） |

---

## 7. 承認ワークフロー

### 7.1 approval_policies

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| ポリシーID | policy_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 文書種別 | document_type | VARCHAR(50) | ✅ | `payment_request`/`expense`/`journal` |
| 最小金額 | min_amount | NUMERIC(15,2) | ✅ | この金額以上の申請に適用 |
| 最大金額 | max_amount | NUMERIC(15,2) | — | 上限額（NULL=無限） |
| 承認ロールID | approver_role_id | UUID | ✅ FK | 承認が必要なロール |
| ステップ番号 | step_number | INT | ✅ | 承認順序（1=1次, 2=2次） |
| 有効フラグ | is_active | BOOLEAN | ✅ | — |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |

### 7.2 approval_requests

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 承認依頼ID | request_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 文書種別 | document_type | VARCHAR(50) | ✅ | `payment_request`/`expense`/`journal` |
| 文書ID | document_id | UUID | ✅ | 仕訳ヘッダIDや支払申請ID |
| 申請者ID | requester_id | UUID | ✅ FK | 起票者 |
| 現在ステップ | current_step | INT | ✅ | 現在の承認ステップ番号 |
| 状態 | status | VARCHAR(20) | ✅ | `pending`/`approved`/`rejected`/`withdrawn` |
| 承認者ID | approved_by | UUID | — FK | 最終承認者 |
| 承認日時 | approved_at | TIMESTAMPTZ | — | — |
| 差戻し理由 | rejection_reason | TEXT | — | — |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | 申請日時 |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

---

## 8. 支払・銀行

### 8.1 bank_accounts

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 口座ID | bank_account_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 銀行コード | bank_code | VARCHAR(4) | ✅ | 金融機関コード |
| 支店コード | branch_code | VARCHAR(3) | ✅ | 支店コード |
| 口座種別 | account_type | VARCHAR(10) | ✅ | `ordinary`(普通)/`current`(当座)/`savings`(貯金) |
| 口座番号 | account_no_encrypted | BYTEA | ✅ | 暗号化保管された口座番号 |
| 口座名義 | account_name | VARCHAR(100) | ✅ | 口座名義人 |
| 口座名義カナ | account_name_kana | VARCHAR(40) | ✅ | 半角カナ（全銀フォーマット用） |
| 通貨コード | currency_code | VARCHAR(3) | ✅ | `JPY`等 |
| 利用開始日 | valid_from | DATE | ✅ | — |
| 利用終了日 | valid_to | DATE | — | — |
| 自動取得設定 | auto_fetch_enabled | BOOLEAN | ✅ | 銀行明細の自動取得を有効にするか |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

### 8.2 bank_statement_details

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 明細ID | statement_detail_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 口座ID | bank_account_id | UUID | ✅ FK | 対象口座 |
| 勘定日 | value_date | DATE | ✅ | 取引日（値決日） |
| 出金額 | withdraw_amount | NUMERIC(15,2) | ✅ | 支払額（0の場合あり） |
| 入金額 | deposit_amount | NUMERIC(15,2) | ✅ | 入金額（0の場合あり） |
| 振込人名カナ | sender_name_kana | VARCHAR(150) | ✅ | 振込人名（半角カナ） |
| 摘要 | description | TEXT | — | 銀行明細の摘要 |
| 消込済フラグ | is_reconciled | BOOLEAN | ✅ | 消込完了かどうか |
| 消込先仕訳ID | reconciled_journal_header_id | UUID | — FK | 消込先の仕訳 |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |

### 8.3 payment_requests

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 支払申請ID | payment_request_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 取引先ID | partner_id | UUID | — FK | 支払先取引先 |
| 支払日 | payment_date | DATE | ✅ | 支払予定日 |
| 支払金額 | payment_amount | NUMERIC(15,2) | ✅ | 支払金額 |
| 振込元口座ID | bank_account_id | UUID | — FK | 振込元口座 |
| 振込先銀行コード | dest_bank_code | VARCHAR(4) | — | 被仕向金融機関コード |
| 振込先支店コード | dest_branch_code | VARCHAR(3) | — | 被仕向支店コード |
| 振込先口座種別 | dest_account_type | VARCHAR(10) | — | — |
| 振込先口座番号 | dest_account_no | VARCHAR(7) | — | — |
| 振込先口座名義カナ | dest_account_name_kana | VARCHAR(30) | — | 半角カナ |
| 状態 | status | VARCHAR(20) | ✅ | `draft`/`pending_approval`/`approved`/`executed`/`failed` |
| 紐付け仕訳ID | journal_header_id | UUID | — FK | 関連仕訳 |
| 全銀出力バッチID | zengin_export_batch_id | UUID | — | 全銀データ出力バッチのID |
| 起票者ID | created_by | UUID | ✅ FK | 申請作成者 |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

---

## 9. 固定資産

### 9.1 fixed_assets

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 資産ID | asset_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 資産管理番号 | asset_code | VARCHAR(50) | ✅ | 会社内一意の資産コード |
| 資産名 | asset_name | VARCHAR(255) | ✅ | 資産名称 |
| 取得年月日 | acquisition_date | DATE | ✅ | — |
| 取得価額 | acquisition_cost | NUMERIC(15,2) | ✅ | — |
| 償却方法 | depreciation_method | VARCHAR(20) | ✅ | `straight_line`/`declining_balance`/`double_declining` |
| 耐用年数 | useful_life | INT | ✅ | 年数 |
| 残存価額 | salvage_value | NUMERIC(15,2) | — | 現行税法では原則1円まで償却可能 |
| 累計償却額 | accumulated_depreciation | NUMERIC(15,2) | ✅ | 期首減価償却累計額 |
| 当期償却額 | current_year_depreciation | NUMERIC(15,2) | ✅ | 当期減価償却額 |
| 部門ID | department_id | UUID | — FK | 使用部門 |
| 状態 | status | VARCHAR(20) | ✅ | `active`/`retired`/`sold` |
| 除却日 | retired_date | DATE | — | — |
| 除却理由 | retire_reason | TEXT | — | — |
| 紐付け仕訳ID | journal_header_id | UUID | — FK | 償却仕訳への参照 |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

---

## 10. 給与

### 10.1 employees

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 社員ID | employee_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 社員コード | employee_code | VARCHAR(20) | ✅ | 会社内一意の社員コード |
| 姓 | last_name | VARCHAR(50) | ✅ | — |
| 名 | first_name | VARCHAR(50) | ✅ | — |
| 姓カナ | last_name_kana | VARCHAR(50) | ✅ | — |
| 名カナ | first_name_kana | VARCHAR(50) | ✅ | — |
| 生年月日 | birth_date | DATE | ✅ | — |
| 性別 | gender | VARCHAR(10) | ✅ | `male`/`female` |
| マイナンバー | my_number_encrypted | BYTEA | — | 暗号化保管 |
| 健康保険番号 | health_insurance_no | VARCHAR(20) | — | — |
| 年金番号 | pension_no | VARCHAR(20) | — | — |
| 入社日 | hire_date | DATE | ✅ | — |
| 退社日 | retire_date | DATE | — | — |
| 部門ID | department_id | UUID | — FK | 所属部門 |
| 基本給月額 | monthly_salary | NUMERIC(15,2) | ✅ | 月額基本給 |
| 有効フラグ | is_active | BOOLEAN | ✅ | 在籍中かどうか |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

### 10.2 payroll_records

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 給与ID | payroll_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 社員ID | employee_id | UUID | ✅ FK | 対象社員 |
| 対象年 | target_year | INT | ✅ | 給与計算対象年 |
| 対象月 | target_month | INT | ✅ | 給与計算対象月 |
| 基本給 | base_salary | NUMERIC(15,2) | ✅ | — |
| 残業代 | overtime_pay | NUMERIC(15,2) | ✅ | — |
| 諸手当合計 | allowance_total | NUMERIC(15,2) | ✅ | — |
| 健康保険料 | deduction_health_insurance | NUMERIC(15,2) | ✅ | 控除額 |
| 厚生年金保険料 | deduction_pension | NUMERIC(15,2) | ✅ | 控除額 |
| 雇用保険料 | deduction_employment_insurance | NUMERIC(15,2) | ✅ | 控除額 |
| 源泉所得税 | deduction_income_tax | NUMERIC(15,2) | ✅ | 控除額 |
| 住民税 | deduction_resident_tax | NUMERIC(15,2) | ✅ | 控除額 |
| 控除合計 | deduction_total | NUMERIC(15,2) | ✅ | — |
| 差引支給額 | net_pay | NUMERIC(15,2) | ✅ | 手取り額 |
| 紐付け仕訳ID | journal_header_id | UUID | — FK | 給与仕訳 |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

---

## 11. 事務タスク

### 11.1 office_tasks

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| タスクID | task_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| タスク種別 | task_type | VARCHAR(50) | ✅ | `employee_onboarding`/`expense_claim`/`insurance_qualify` |
| 関連社員ID | related_employee_id | UUID | — FK | 関連する従業員 |
| 関連ドキュメントID | related_document_id | UUID | — FK | 関連する証憑 |
| 状態 | status | VARCHAR(20) | ✅ | `pending`/`in_progress`/`completed`/`cancelled` |
| 担当者ID | assigned_to | UUID | — FK | 担当ユーザー |
| メタデータ | meta_data | JSONB | — | タスク種別に応じた動的データ |
| 期限日 | due_date | DATE | — | — |
| 完了日時 | completed_at | TIMESTAMPTZ | — | — |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

---

## 12. 監査・検知

### 12.1 audit_detection_logs

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 検知ID | detection_id | UUID | ✅ PK | 一意識別子 |
| 会社ID | company_id | UUID | ✅ FK | 所属会社 |
| 仕訳ヘッダID | journal_header_id | UUID | ✅ FK | 対象仕訳 |
| リスクレベル | risk_level | VARCHAR(20) | ✅ | `critical`/`warning`/`info` |
| 検知カテゴリ | detection_category | VARCHAR(50) | ✅ | `duplicate`/`irregular_time`/`circular_transaction` |
| 検知理由 | reason_description | TEXT | ✅ | 検知理由の解説テキスト |
| 確認者ID | reviewer_user_id | UUID | — FK | 確認した監査担当者 |
| 確認状態 | review_status | VARCHAR(20) | ✅ | `unreviewed`/`confirmed_ok`/`needs_correction` |
| 確認日時 | reviewed_at | TIMESTAMPTZ | — | — |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | 検知日時 |

---

## 13. セキュリティ

### 13.1 tenant_security_policies

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| ポリシーID | policy_id | UUID | ✅ PK | 一意識別子 |
| テナントID | tenant_id | UUID | ✅ UNIQUE FK | 所属テナント（1:1） |
| 認証方式 | auth_type | VARCHAR(20) | ✅ | `password`/`saml`/`oidc` |
| SSO発行者URL | sso_issuer_url | VARCHAR(512) | — | SSOプロバイダーのメタデータURL |
| SSOクライアントID | sso_client_id | VARCHAR(255) | — | — |
| SSOクライアントシークレット | sso_client_secret_encrypted | BYTEA | — | 暗号化保管 |
| MFA強制 | mfa_required | BOOLEAN | ✅ | 多要素認証の強制有無 |
| 許可IP帯域リスト | allowed_ip_ranges | TEXT[] | — | CIDR表記の配列（例: `{"192.168.1.0/24"}`） |
| セッションタイムアウト | session_timeout_minutes | INT | ✅ | 分（デフォルト: 60） |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

---

## 14. API冪等性

### 14.1 idempotency_keys

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| キーID | key_id | UUID | ✅ PK | 一意識別子 |
| 冪等キー | idempotency_key | VARCHAR(255) | ✅ | クライアントが生成した一意識別子 |
| テナントID | tenant_id | UUID | ✅ | 所属テナント |
| リクエストパス | request_path | VARCHAR(255) | ✅ | リクエスト先エンドポイント |
| リクエストハッシュ | request_hash | CHAR(64) | ✅ | パラメータのSHA-256ハッシュ |
| 処理状態 | status | VARCHAR(20) | ✅ | `processing`/`completed`/`failed` |
| レスポンスステータス | response_status | INT | — | 返却したHTTPステータス |
| レスポンスボディ | response_body | TEXT | — | 返却したレスポンスJSON |
| 有効期限 | expires_at | TIMESTAMPTZ | ✅ | キャッシュ有効期限（通常24時間後） |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |

---

## 15. Webhook

### 15.1 webhook_endpoints

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| エンドポイントID | endpoint_id | UUID | ✅ PK | 一意識別子 |
| テナントID | tenant_id | UUID | ✅ | 所属テナント |
| 通知先URL | target_url | VARCHAR(512) | ✅ | 通知先の外部URL |
| 秘密鍵 | secret_token | VARCHAR(255) | ✅ | HMAC署名生成用 |
| サブスクライブイベント | subscribed_events | TEXT[] | ✅ | 購読イベント種別配列 |
| 有効フラグ | is_active | BOOLEAN | ✅ | — |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |

### 15.2 webhook_deliveries

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| 配信ID | delivery_id | UUID | ✅ PK | 一意識別子 |
| エンドポイントID | endpoint_id | UUID | ✅ FK | 送信先（CASCADE削除） |
| イベント種別 | event_type | VARCHAR(50) | ✅ | `journal.posted`等 |
| ペイロード | payload | JSONB | ✅ | 送信する通知メッセージ本体 |
| 状態 | status | VARCHAR(20) | ✅ | `pending`/`sending`/`succeeded`/`failed_retry`/`dead` |
| 再試行回数 | retry_count | INT | ✅ | 現在までの再試行回数 |
| 最大再試行回数 | max_retries | INT | ✅ | デフォルト5 |
| 次回実行時刻 | next_attempt_at | TIMESTAMPTZ | ✅ | 次回リトライ予定時刻 |
| 最終レスポンスステータス | last_response_status | INT | — | — |
| 最終レスポンスボディ | last_response_body | TEXT | — | — |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |

---

## 16. ライセンス

### 16.1 licenses

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| ライセンスID | license_id | UUID | ✅ PK | 一意識別子 |
| テナントID | tenant_id | UUID | ✅ FK | 所属テナント |
| ライセンス種別 | license_type | VARCHAR(20) | ✅ | `standard`/`enterprise`/`trial` |
| 最大ユーザー数 | max_users | INT | — | — |
| 最大会社数 | max_companies | INT | — | — |
| 月次AI推論上限 | max_ai_inferences_per_month | INT | — | — |
| 月次API呼出上限 | max_api_calls_per_month | INT | — | — |
| ストレージ上限GB | max_storage_gb | INT | — | — |
| 有効モジュール | allowed_modules | TEXT[] | — | 有効化されているモジュールリスト |
| 適用開始日 | valid_from | DATE | ✅ | — |
| 適用終了日 | valid_to | DATE | — | — |
| 有効フラグ | is_active | BOOLEAN | ✅ | — |
| 作成日時 | created_at | TIMESTAMPTZ | ✅ | — |

### 16.2 usage_counters

| 論理名 | 物理名 | 型 | 必須 | 説明 |
|--------|--------|-----|------|------|
| カウンタID | counter_id | UUID | ✅ PK | 一意識別子 |
| テナントID | tenant_id | UUID | ✅ | 所属テナント |
| カウンタ種別 | counter_type | VARCHAR(30) | ✅ | `ai_inference`/`api_call`/`storage` |
| 集計期間 | counter_period | VARCHAR(10) | ✅ | `2026-06`等 |
| カウント値 | count_value | BIGINT | ✅ | 累計カウント |
| 更新日時 | updated_at | TIMESTAMPTZ | ✅ | — |

---

## 17. 業務用語集

| 用語 | 英語 | 説明 |
|------|------|------|
| 仕訳 | Journal Entry | 複式簿記における取引の記録（借方・貸方のペア） |
| 借方 | Debit | 仕訳の左側（資産の増加・費用の発生等） |
| 貸方 | Credit | 仕訳の右側（負債の増加・収益の発生等） |
| 勘定科目 | Account | 取引を分類するための科目（現金、売上等） |
| 補助科目 | Sub Account | 勘定科目をさらに細分化した科目 |
| 試算表 | Trial Balance (TB) | 全勘定科目の残高一覧 |
| 総勘定元帳 | General Ledger | 全取引を勘定科目別に集計した帳簿 |
| 決算 | Closing | 期末における財務諸表の作成手続き |
| 消込 | Reconciliation | 入出金明細と売掛金/買掛金を突き合わせて清算すること |
| 起票 | Entry | 伝票・仕訳を新規作成すること |
| 承認 | Approval | 上位権限者が内容を確認し承認すること |
| 職務分掌 | Segregation of Duties (SoD) | 不正防止のため、起票者と承認者を分離すること |
| 適格請求書 | Qualified Invoice | インボイス制度に基づく登録番号付き請求書 |
| 電子帳簿保存法 | e-Book Preservation Law | 電子データによる帳簿・証憑の保存に関する法令 |
| 減価償却 | Depreciation | 固定資産の取得価額を耐用年数にわたり費用配分すること |
| 損金不算入 | Non-deductible Expense | 税務上、課税所得から控除されない支出（交際費等） |
| 全銀フォーマット | Zengin Format | 日本の銀行間データ通信の標準フォーマット（固定長120バイト） |
| 任意時点復元 | Point-in-Time Recovery (PITR) | DBを過去の特定時点の状態に復元する機能 |
| 冪等性 | Idempotency | 同一リクエストを複数回実行しても結果が同一である性質 |
| RPO | Recovery Point Objective | 目標復旧時点（データ損失を許容する最大時間） |
| RTO | Recovery Time Objective | 目標復旧時間（復旧に要する最大時間） |
