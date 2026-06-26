# kAIkei — OpenAPI 仕様書

> 本ドキュメントはkAIkeiの主要APIエンドポイントをOpenAPI 3.1形式で定義する。
> 実装時はこの仕様を基にコントラクトファースト開発を行う。

---

## 1. 共通仕様

### 1.1 サーバーURL

| 環境 | ベースURL |
|------|----------|
| 開発 | `http://localhost:8000/api/v1` |
| ステージング | `https://staging-api.cotton-erp.com/api/v1` |
| 本番 | `https://api.cotton-erp.com/api/v1` |

### 1.2 認証

```yaml
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: "JWT Bearer Token（ログインAPIで取得）"
```

### 1.3 共通ヘッダー

| ヘッダー | 必須 | 説明 |
|---------|------|------|
| `Authorization` | ✅ | `Bearer {JWT}` |
| `Idempotency-Key` | POST/PUT時推奨 | UUID形式の冪等キー |
| `X-Request-ID` | 任意 | トレーシング用リクエストID |

### 1.4 共通エラーレスポンス（RFC 7807準拠）

```json
{
  "type": "https://cotton-erp.com/errors/validation",
  "title": "Validation Error",
  "status": 400,
  "detail": "貸借の合計金額が一致しません。",
  "instance": "/api/v1/journals",
  "errors": [
    {
      "rule_id": "VAL-001",
      "message": "貸借の合計金額が一致しません。借方: 11000円, 貸方: 10000円",
      "level": "critical"
    }
  ]
}
```

### 1.5 ページネーション

```
GET /api/v1/journals?page=1&page_size=50&sort=-transaction_date
```

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `page` | int | 1 | ページ番号 |
| `page_size` | int | 50 | 1ページあたり件数（最大200） |
| `sort` | string | — | ソート項目（`-`プレフィックスで降順） |

レスポンスヘッダー：
```
X-Total-Count: 1500
X-Page: 1
X-Page-Size: 50
X-Total-Pages: 30
```

---

## 2. 認証API

### POST /auth/login

```yaml
post:
  summary: ログイン
  description: メールアドレスとパスワードで認証し、JWTを取得する
  tags: [Auth]
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [email, password]
          properties:
            email:
              type: string
              format: email
            password:
              type: string
              format: password
  responses:
    '200':
      description: 認証成功
      content:
        application/json:
          schema:
            type: object
            properties:
              access_token:
                type: string
              refresh_token:
                type: string
              expires_in:
                type: integer
                example: 3600
              user:
                $ref: '#/components/schemas/User'
    '401':
      description: 認証失敗
```

### POST /auth/refresh

```yaml
post:
  summary: トークンリフレッシュ
  tags: [Auth]
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [refresh_token]
          properties:
            refresh_token:
              type: string
  responses:
    '200':
      description: 新しいアクセストークン
```

### POST /auth/sso/callback

```yaml
post:
  summary: SSOコールバック（SAML/OIDC）
  tags: [Auth]
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          properties:
            saml_response:
              type: string
            code:
              type: string
              description: OIDC認可コード
            state:
              type: string
  responses:
    '200':
      description: SSO認証成功・JWT発行
```

---

## 3. 仕訳API

### POST /journals

```yaml
post:
  summary: 仕訳作成
  description: 新規仕訳を作成する。バリデーションエンジン（VAL-001〜005）を通過後に登録される。
  tags: [Journals]
  security:
    - BearerAuth: []
  parameters:
    - name: Idempotency-Key
      in: header
      required: true
      schema:
        type: string
        format: uuid
  requestBody:
    required: true
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/JournalCreateRequest'
  responses:
    '201':
      description: 作成成功
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/JournalResponse'
    '400':
      description: バリデーションエラー（VAL-001〜005）
    '409':
      description: 冪等キーの重複リクエスト
```

### GET /journals

```yaml
get:
  summary: 仕訳一覧取得
  tags: [Journals]
  security:
    - BearerAuth: []
  parameters:
    - name: company_id
      in: query
      required: true
      schema:
        type: string
        format: uuid
    - name: transaction_date_from
      in: query
      schema:
        type: string
        format: date
    - name: transaction_date_to
      in: query
      schema:
        type: string
        format: date
    - name: approval_status
      in: query
      schema:
        type: string
        enum: [draft, waiting_approval, approved, posted, void]
    - name: account_code
      in: query
      schema:
        type: string
    - name: page
      in: query
      schema:
        type: integer
        default: 1
    - name: page_size
      in: query
      schema:
        type: integer
        default: 50
    - name: sort
      in: query
      schema:
        type: string
        default: -transaction_date
  responses:
    '200':
      description: 仕訳一覧
      headers:
        X-Total-Count:
          schema:
            type: integer
      content:
        application/json:
          schema:
            type: array
            items:
              $ref: '#/components/schemas/JournalResponse'
```

### GET /journals/{journal_header_id}

```yaml
get:
  summary: 仕訳詳細取得
  tags: [Journals]
  security:
    - BearerAuth: []
  parameters:
    - name: journal_header_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
  responses:
    '200':
      description: 仕訳詳細
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/JournalResponse'
    '404':
      description: 仕訳が見つからない
```

### PUT /journals/{journal_header_id}/approve

```yaml
put:
  summary: 仕訳承認
  description: 仕訳を承認状態に変更する。SoDチェック（起票者≠承認者）を実行する。
  tags: [Journals]
  security:
    - BearerAuth: []
  parameters:
    - name: journal_header_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
  requestBody:
    content:
      application/json:
        schema:
          type: object
          properties:
            comment:
              type: string
  responses:
    '200':
      description: 承認成功
    '403':
      description: SoD違反（起票者と承認者が同一）
    '409':
      description: 承認対象外のステータス
```

### PUT /journals/{journal_header_id}/void

```yaml
put:
  summary: 仕訳無効化（逆仕訳）
  tags: [Journals]
  security:
    - BearerAuth: []
  parameters:
    - name: journal_header_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [reason]
          properties:
            reason:
              type: string
  responses:
    '200':
      description: 無効化成功
```

---

## 4. AI仕訳推論API

### POST /ai/suggest-journal

```yaml
post:
  summary: AI仕訳推論
  description: OCR抽出テキストと勘定科目マスタを入力とし、AIが仕訳提案を返す。
  tags: [AI]
  security:
    - BearerAuth: []
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [company_id, ocr_extracted_text]
          properties:
            company_id:
              type: string
              format: uuid
            ocr_extracted_text:
              type: string
            source_file_id:
              type: string
              format: uuid
            accounts_context:
              type: array
              items:
                type: object
                properties:
                  code:
                    type: string
                  name:
                    type: string
  responses:
    '200':
      description: AI仕訳提案
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/AIJournalSuggestion'
    '422':
      description: OCRテキストの解析失敗
```

### GET /ai/inference-logs

```yaml
get:
  summary: AI推論ログ一覧取得
  tags: [AI]
  security:
    - BearerAuth: []
  parameters:
    - name: company_id
      in: query
      required: true
      schema:
        type: string
        format: uuid
    - name: applied_status
      in: query
      schema:
        type: string
        enum: [pending_review, applied, rejected, modified]
    - name: date_from
      in: query
      schema:
        type: string
        format: date
    - name: date_to
      in: query
      schema:
        type: string
        format: date
  responses:
    '200':
      description: AI推論ログ一覧
```

### PUT /ai/inference-logs/{inference_id}/apply

```yaml
put:
  summary: AI推論結果の適用（仕訳化）
  description: AI推論ログの提案内容で実際の仕訳を作成する。
  tags: [AI]
  security:
    - BearerAuth: []
  parameters:
    - name: inference_id
      in: path
      required: true
      schema:
        type: string
        format: uuid
  requestBody:
    content:
      application/json:
        schema:
          type: object
          properties:
            modified_lines:
              type: array
              description: ユーザーが修正した場合の明細
              items:
                $ref: '#/components/schemas/JournalLine'
  responses:
    '201':
      description: 仕訳作成成功
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/JournalResponse'
```

---

## 5. 証憑アーカイブAPI

### POST /documents/archive

```yaml
post:
  summary: 証憑ファイルアーカイブ
  description: PDF/画像をアップロードし、SHA-256ハッシュを計算して電帳法準拠でアーカイブする。
  tags: [Documents]
  security:
    - BearerAuth: []
  requestBody:
    required: true
    content:
      multipart/form-data:
        schema:
          type: object
          required: [file, company_id, transaction_date, transaction_amount, counterparty_name]
          properties:
            file:
              type: string
              format: binary
            company_id:
              type: string
              format: uuid
            transaction_date:
              type: string
              format: date
            transaction_amount:
              type: number
            counterparty_name:
              type: string
            document_type:
              type: string
              enum: [invoice, receipt, contract, other]
  responses:
    '201':
      description: アーカイブ成功
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ArchivedDocument'
```

### GET /documents/search

```yaml
get:
  summary: 電帳法3軸検索
  description: 取引年月日・取引金額・取引先名称による複数条件検索
  tags: [Documents]
  security:
    - BearerAuth: []
  parameters:
    - name: company_id
      in: query
      required: true
      schema:
        type: string
        format: uuid
    - name: transaction_date_from
      in: query
      schema:
        type: string
        format: date
    - name: transaction_date_to
      in: query
      schema:
        type: string
        format: date
    - name: amount_min
      in: query
      schema:
        type: number
    - name: amount_max
      in: query
      schema:
        type: number
    - name: counterparty_name
      in: query
      schema:
        type: string
        description: 部分一致検索
  responses:
    '200':
      description: 検索結果
```

---

## 6. データインポートAPI

### POST /import/yayoi

```yaml
post:
  summary: 弥生会計CSV取り込み
  tags: [Import]
  security:
    - BearerAuth: []
  requestBody:
    required: true
    content:
      multipart/form-data:
        schema:
          type: object
          required: [file, company_id]
          properties:
            file:
              type: string
              format: binary
            company_id:
              type: string
              format: uuid
            dry_run:
              type: boolean
              default: true
              description: true=シミュレーションのみ（DB書き込みなし）
  responses:
    '200':
      description: 取り込み結果（Dry-runレポート含む）
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ImportSimulationResult'
```

### POST /import/simulate

```yaml
post:
  summary: 取り込みシミュレーション
  description: 実際のDB書き込みを行わず、マッピングエラーや存在しない科目のリストを返す。
  tags: [Import]
  security:
    - BearerAuth: []
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [company_id, csv_data]
          properties:
            company_id:
              type: string
              format: uuid
            csv_data:
              type: string
            import_format:
              type: string
              enum: [yayoi, freee, mf, dreamvisor]
  responses:
    '200':
      description: シミュレーション結果
```

---

## 7. 支払API

### POST /payments/zengin-export

```yaml
post:
  summary: 全銀フォーマット生成
  description: 承認済みの支払申請から全銀協フォーマット（固定長120バイト）のファイルを生成する。
  tags: [Payments]
  security:
    - BearerAuth: []
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [company_id, payment_date, bank_account_id]
          properties:
            company_id:
              type: string
              format: uuid
            payment_date:
              type: string
              format: date
            bank_account_id:
              type: string
              format: uuid
            payment_request_ids:
              type: array
              items:
                type: string
                format: uuid
  responses:
    '200':
      description: 全銀データ生成成功
      content:
        application/octet-stream:
          schema:
            type: string
            format: binary
```

### POST /bank/reconcile

```yaml
post:
  summary: 自動消込実行
  description: 銀行明細と入金予定/支払予定をマッチングし、消込候補を返す。
  tags: [Bank]
  security:
    - BearerAuth: []
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [company_id]
          properties:
            company_id:
              type: string
              format: uuid
            bank_account_id:
              type: string
              format: uuid
            date_from:
              type: string
              format: date
            date_to:
              type: string
              format: date
  responses:
    '200':
      description: 消込候補リスト
      content:
        application/json:
          schema:
            type: array
            items:
              type: object
              properties:
                statement_detail_id:
                  type: string
                  format: uuid
                candidates:
                  type: array
                  items:
                    type: object
                    properties:
                      schedule_id:
                        type: string
                      score:
                        type: number
                      reason:
                        type: string
```

---

## 8. 固定資産API

### POST /assets/depreciate

```yaml
post:
  summary: 月次減価償却実行
  description: 全有効資産の当月償却額を計算し、償却仕訳を自動生成する。
  tags: [Assets]
  security:
    - BearerAuth: []
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [company_id, target_year, target_month]
          properties:
            company_id:
              type: string
              format: uuid
            target_year:
              type: integer
            target_month:
              type: integer
            dry_run:
              type: boolean
              default: false
  responses:
    '200':
      description: 償却計算結果・生成仕訳リスト
```

---

## 9. 給与API

### POST /payroll/calculate

```yaml
post:
  summary: 給与計算実行
  description: 指定月の全社員の給与・社会保険料・源泉所得税を計算する。
  tags: [Payroll]
  security:
    - BearerAuth: []
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [company_id, target_year, target_month]
          properties:
            company_id:
              type: string
              format: uuid
            target_year:
              type: integer
            target_month:
              type: integer
            generate_journal:
              type: boolean
              default: true
              description: 給与仕訳を自動生成するか
  responses:
    '200':
      description: 給与計算結果
```

---

## 10. 税務API

### GET /tax/forecast

```yaml
get:
  summary: 税額予測・リスク検知
  description: 現時点の試算表から当期末の着地利益・税額を推計し、税務リスクを検知する。
  tags: [Tax]
  security:
    - BearerAuth: []
  parameters:
    - name: company_id
      in: query
      required: true
      schema:
        type: string
        format: uuid
    - name: forecast_factor
      in: query
      schema:
        type: number
        default: 1.0
        description: 残り期間係数（例: 10ヶ月経過時 12/10=1.2）
  responses:
    '200':
      description: 税額予測結果
      content:
        application/json:
          schema:
            type: object
            properties:
              forecasted_profit_before_tax:
                type: number
              estimated_taxable_income:
                type: number
              estimated_tax_amount:
                type: number
              tax_risk_warnings:
                type: array
                items:
                  type: string
```

---

## 11. 監査API

### POST /audit/inspect

```yaml
post:
  summary: リアルタイム監査検知
  description: 仕訳に対し重複・深夜入力・循環取引等のリスク判定を実行する。
  tags: [Audit]
  security:
    - BearerAuth: []
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [journal_header_id]
          properties:
            journal_header_id:
              type: string
              format: uuid
  responses:
    '200':
      description: 検知結果
      content:
        application/json:
          schema:
            type: array
            items:
              type: object
              properties:
                risk_level:
                  type: string
                  enum: [critical, warning, info]
                category:
                  type: string
                reason:
                  type: string
```

### POST /audit/ledger-check

```yaml
post:
  summary: 帳簿一貫性検証バッチ
  description: 全仕訳の貸借一致・集計キャッシュとの突合を実行し、ドリフトを検知する。
  tags: [Audit]
  security:
    - BearerAuth: []
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [company_id, target_date]
          properties:
            company_id:
              type: string
              format: uuid
            target_date:
              type: string
              format: date
  responses:
    '200':
      description: 検証結果
```

---

## 12. エクスポートAPI

### POST /export/audit-package

```yaml
post:
  summary: 監査データ一括エクスポート
  description: 指定年度の総勘定元帳CSV・証憑インデックスCSV・証憑ファイル群をZIPで出力する。
  tags: [Export]
  security:
    - BearerAuth: []
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [company_id, fiscal_year]
          properties:
            company_id:
              type: string
              format: uuid
            fiscal_year:
              type: integer
  responses:
    '200':
      description: ZIPファイル
      content:
        application/zip:
          schema:
            type: string
            format: binary
```

---

## 13. Webhook API

### POST /webhooks/endpoints

```yaml
post:
  summary: Webhookエンドポイント登録
  tags: [Webhooks]
  security:
    - BearerAuth: []
  requestBody:
    required: true
    content:
      application/json:
        schema:
          type: object
          required: [target_url, secret_token, subscribed_events]
          properties:
            target_url:
              type: string
              format: uri
            secret_token:
              type: string
            subscribed_events:
              type: array
              items:
                type: string
              example: ["journal.posted", "payroll.closed"]
  responses:
    '201':
      description: 登録成功
```

### GET /webhooks/deliveries

```yaml
get:
  summary: Webhook配信履歴取得
  tags: [Webhooks]
  security:
    - BearerAuth: []
  parameters:
    - name: status
      in: query
      schema:
        type: string
        enum: [pending, sending, succeeded, failed_retry, dead]
    - name: endpoint_id
      in: query
      schema:
        type: string
        format: uuid
  responses:
    '200':
      description: 配信履歴一覧
```

---

## 14. スキーマ定義

### 14.1 JournalCreateRequest

```yaml
components:
  schemas:
    JournalCreateRequest:
      type: object
      required: [company_id, transaction_date, slip_type, lines]
      properties:
        company_id:
          type: string
          format: uuid
        transaction_date:
          type: string
          format: date
        slip_type:
          type: string
          enum: [transfer, receipt, payment]
        summary:
          type: string
        lines:
          type: array
          minItems: 2
          items:
            $ref: '#/components/schemas/JournalLine'
```

### 14.2 JournalLine

```yaml
    JournalLine:
      type: object
      required: [entry_type, account_code, tax_type_code, amount_excluding_tax, tax_amount, amount_including_tax]
      properties:
        line_no:
          type: integer
        entry_type:
          type: string
          enum: [debit, credit]
        account_code:
          type: string
        sub_account_code:
          type: string
        department_id:
          type: string
          format: uuid
        project_id:
          type: string
          format: uuid
        partner_id:
          type: string
          format: uuid
        tax_type_code:
          type: string
          example: tax_10_in
        invoice_category:
          type: string
          enum: [qualified, transitional_80, transitional_50, unqualified]
          default: qualified
        amount_excluding_tax:
          type: number
          format: double
        tax_amount:
          type: number
          format: double
        amount_including_tax:
          type: number
          format: double
        summary:
          type: string
```

### 14.3 JournalResponse

```yaml
    JournalResponse:
      type: object
      properties:
        journal_header_id:
          type: string
          format: uuid
        company_id:
          type: string
          format: uuid
        journal_no:
          type: string
        transaction_date:
          type: string
          format: date
        slip_type:
          type: string
        approval_status:
          type: string
          enum: [draft, waiting_approval, approved, posted, void]
        created_by:
          type: string
          format: uuid
        approved_by:
          type: string
          format: uuid
        is_voided:
          type: boolean
        source_type:
          type: string
        lines:
          type: array
          items:
            $ref: '#/components/schemas/JournalLine'
        validation_errors:
          type: array
          items:
            type: object
            properties:
              rule_id:
                type: string
              message:
                type: string
              level:
                type: string
                enum: [critical, warning]
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time
```

### 14.4 AIJournalSuggestion

```yaml
    AIJournalSuggestion:
      type: object
      properties:
        inference_id:
          type: string
          format: uuid
        suggested_date:
          type: string
          format: date
        confidence_score:
          type: number
          format: float
          minimum: 0
          maximum: 100
        inference_reason:
          type: string
          description: AI説明責任：推論理由
        model_name:
          type: string
        model_version:
          type: string
        journal_proposal:
          type: object
          properties:
            slip_type:
              type: string
            lines:
              type: array
              items:
                type: object
                properties:
                  line_no:
                    type: integer
                  entry_type:
                    type: string
                    enum: [debit, credit]
                  account_code:
                    type: string
                  account_name_estimated:
                    type: string
                  tax_type_code:
                    type: string
                  invoice_category:
                    type: string
                  amount_excluding_tax:
                    type: number
                  tax_amount:
                    type: number
                  amount_including_tax:
                    type: number
                  summary:
                    type: string
```

### 14.5 ArchivedDocument

```yaml
    ArchivedDocument:
      type: object
      properties:
        document_id:
          type: string
          format: uuid
        file_path:
          type: string
        file_hash:
          type: string
          description: SHA-256
        transaction_date:
          type: string
          format: date
        transaction_amount:
          type: number
        counterparty_name:
          type: string
        document_type:
          type: string
        timestamp_token:
          type: string
        created_at:
          type: string
          format: date-time
```

### 14.6 ImportSimulationResult

```yaml
    ImportSimulationResult:
      type: object
      properties:
        status:
          type: string
          enum: [success, warning_contained, failed]
        total_rows_scanned:
          type: integer
        success_rows_drafted:
          type: integer
        failed_rows:
          type: integer
        issues:
          type: array
          items:
            type: object
            properties:
              row_index:
                type: integer
              error_code:
                type: string
              details:
                type: string
```

### 14.7 User

```yaml
    User:
      type: object
      properties:
        user_id:
          type: string
          format: uuid
        email:
          type: string
        display_name:
          type: string
        roles:
          type: array
          items:
            type: object
            properties:
              role_code:
                type: string
              role_name:
                type: string
              company_id:
                type: string
                format: uuid
```

---

## 15. イベント種別（Webhook通知用）

| イベント名 | 発生タイミング |
|-----------|--------------|
| `journal.posted` | 仕訳が確定（posted）になった時 |
| `journal.voided` | 仕訳が無効化された時 |
| `approval.requested` | 承認依頼が発生した時 |
| `approval.completed` | 承認が完了した時 |
| `approval.rejected` | 承認が差戻しされた時 |
| `payment.executed` | 支払が実行された時 |
| `payroll.closed` | 給与計算が確定された時 |
| `ai.suggestion_created` | AI仕訳提案が生成された時 |
| `audit.anomaly_detected` | 監査異常が検知された時 |
| `document.archived` | 証憑がアーカイブされた時 |
| `ledger.drift_detected` | 帳簿ドリフトが検知された時 |
| `tax.risk_warning` | 税務リスク警告が発生した時 |
