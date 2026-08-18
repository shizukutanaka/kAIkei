# kAIkei — 改善指示書（Opus / Sonnet セッション実行用）

> 本書は kAIkei（日本向けAI駆動統合バックオフィス/ERP）の現状監査（長所・短所）と、
> 将来の Claude（Opus/Sonnet）セッションがそのまま着手できる改善指示書である。
> 各改善は「背景 / 対象ファイル / 手順 / 検証」を備え、独立に実行可能。
> 着手前に必ず現状を再確認すること（本書はスナップショットであり、実装は進行する）。

## 0. 実行者への共通ルール（必読）

- **全テストをゲートにする**。変更後に必ず:
  - `cd backend && python -m pytest -m "not db" -q`
    （カバレッジは既定で無効。見たいときは `--cov=app --cov-report=term-missing`）
  - ローカルPostgresを起動し `TEST_DATABASE_URL=postgresql+asyncpg://kaikei:kaikei_dev@127.0.0.1:5432/kaikei_test python -m pytest -m db -q`
  - Alembicは新規スクラッチDBで `alembic upgrade head`（単一ヘッド維持）
  - frontend: `npx tsc --noEmit` / `npm run build` / `npm test`
- **1改善 = 1ブランチ = 1PR**。CI（build/test）green を確認してから main へマージ。
- **モデル名・モデルIDはコミットメッセージ/PR/コード/コメントなど、リポジトリに
  push されるあらゆる成果物に含めない**（会話での言及のみ）。
- **日本の税・社保・労保は法令を必ず自分で再確認**（率・端数処理・境界・上限）。
  レビューは「確信できる法令ルールのみ」を数値例つきで報告・修正する。
- `app.main` は現在そのままimportできる（過去に jose→cryptography の PanicException で
  失敗する環境があった）。HTTP経路のテストは `tests/test_tenant_scope_api_db.py` の
  `api` fixture を参考にすること。ミドルウェアが読み込み時のグローバルなエンジンを
  掴んでいるため、テスト用セッションを差し替えないと「別ループのFuture」エラーで
  本来の応答が握り潰される。
- 環境: docker registry 403。ローカルPostgres16バイナリを使用。DBテストのスキーマは
  conftestの `Base.metadata.create_all`（マイグレーション未経由）で作られるため、
  索引など「モデルに書いていない差分」はテストDBに現れない。
  マイグレーション自体の欠落は `tests/test_migration_parity_db.py` が
  使い捨てDBに `alembic upgrade head` して検出する。
- **model↔migration パリティ**は `tests/test_migration_model_parity.py`（静的）と
  `tests/test_migration_parity_db.py`（実際に `alembic upgrade head` して照合）が保証する。
  新モデル・新カラム追加時はマイグレーションも必ず追加。
- **ルート重複ガード**は `backend/tests/test_route_uniqueness.py` が保証する。FastAPIは
  同一パスを先勝ちで解決するため、merge等で重複定義が入ると後続が到達不能な死にコードになる。

### 0-1. コンテナがリセットされた場合の復旧（重要）

実行環境（コンテナ）はセッション中に初期化されることがある。**Gitのコミット済み内容は
無事だが、インストール済みパッケージとPostgresのデータディレクトリは消える**。
`ModuleNotFoundError: No module named 'pytest'` / `sh: 1: next: not found` /
DB接続拒否 が出たら、以下で復旧する（バイナリ自体は残っている）。

```bash
# 1) Python依存（pytest含む）
cd backend && python -m pip install -q -r requirements.txt

# 2) フロント依存
cd ../frontend && npm ci

# 3) Postgres（データディレクトリごと消えるため再作成が必要）
mkdir -p /var/lib/postgresql/pgtest && chown postgres:postgres /var/lib/postgresql/pgtest
su postgres -c "/usr/lib/postgresql/16/bin/initdb -D /var/lib/postgresql/pgtest -A trust"
su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/pgtest \
  -l /var/lib/postgresql/pgtest/server.log -o '-p 5432' -w start"
su postgres -c "/usr/lib/postgresql/16/bin/psql -p 5432 \
  -c \"CREATE ROLE kaikei LOGIN PASSWORD 'kaikei_dev' SUPERUSER;\""
su postgres -c "/usr/lib/postgresql/16/bin/createdb -p 5432 -O kaikei kaikei_test"
```

復旧後は必ず全テストを再実行して、失敗が環境起因でなく実装起因でないことを確認する。

## 1. 長所（強み）

- **レイヤ分離**: 各機能が「DB非依存の純粋関数コア＋非同期DBサービス＋FastAPI＋RBAC＋
  フロント画面」。ビジネスロジックが純粋テスト可能。
- **網羅的ドメイン**: 会計/仕訳/承認/固定資産/インボイス/電帳法/監査/AI に加え、
  給与/賞与/社会保険/労働保険/所得税・消費税・法人税の詳細計算、予算、jobs/ops。
- **法令準拠の計算（アダーサリアルレビュー検証済み）**: 所得税速算表・給与所得控除・
  源泉徴収204条・賞与算出率・社会保険料折半端数・算定基礎届・労働保険年度更新/延納・
  消費税各種（インボイス端数処理・地方消費税22/78・簡易課税・2割特例・経過措置）・
  課税事業者判定・中間申告・法人税予定申告・交際費限度額・定額法償却。
- **信頼性/セキュリティ基盤**: マルチテナント＋RBAC＋監査ログ＋冪等性＋レート制限＋
  IP制限middleware＋MFA(TOTP, RFC6238, リプレイ防止)。2度のセキュリティレビューで
  MFA無効化バイパス・Webhook SSRF・クロステナントアクセス・IP制限詐称等を修正済み。
- **DB整合性ガード**: Alembic単一ヘッド＋model↔migrationパリティ回帰テスト。
- **非同期ワーカー**: Webhook配信＆スケジュールジョブのディスパッチを定期実行
  （`background_jobs.py`、FOR UPDATE SKIP LOCKED で二重処理防止）。
- **フロント**: Next.js 14、WCAG配慮、vitestテスト基盤。

## 2. 短所（弱み）※本書更新時点

### 🔴 最優先（利用者に誤った数字が出る／人手が必要）

- **給与・賞与の源泉所得税、消費税申告が概算のまま**（社会保険料は解消済み）。「給与所得の源泉徴収
  税額表」を扶養親族等の数と甲欄/乙欄で引く必要があるが未実装で、総支給の5%を
  掛けている。**応答の `estimate_notice` と給与画面の警告で「概算」だと明示して
  いる**が、法定計算そのものは未対応。`Employee` に扶養親族等の数・甲乙区分を
  持たせるスキーマ変更から必要（改善7参照）。
- **CIワークフロー本体が未修正**。`.github/workflows/*.yml` は GitHub App に
  `workflows` 権限が無く自動更新できない。現在は編集可能なファイル側の暫定措置で
  回避している（`docs/ci/backend-ci-db-tests.md` 参照）。**人手での適用が必要**で、
  適用したら暫定措置3点を削除すること。
- **DB統合テストがCIで走らない**。`TEST_DATABASE_URL` を渡す `db-test` ジョブが無く、
  テナント分離・監査ログ・マイグレーション整合性など148件がCI未実行。上と同じ理由。

### 🟡 中

- **画面の無いエンドポイントが多い**: 267ルート中166本にフロントの呼び出しが無い。
  特に `/payroll/*` は50本中47本が未使用（純粋な計算APIとして実装されている）。
  「消す」か「画面を作る」かは製品判断。外部利用者がいる可能性があるため
  独断で削除していない。
- **ドキュメントdrift**: `docs/OpenAPISpec.md`・`docs/DataDictionary.md`・
  `docs/DatabaseDesign.md` が実装に追いついていない可能性。

### ⚪ 低

- **マルチレプリカの完全排他なし**: FOR UPDATE SKIP LOCKED で主要窓は閉じたが、
  claim/lease方式の完全な分散ロックではない。
- **Peppol実送信なし**: UBL XML生成のみ。アクセスポイント連携は未実装。
- **本番と検証のPythonバージョン差**: Dockerfile は 3.12、CIと開発環境は 3.11。
  ruff の target-version はサポート下限の py311 に合わせてある。

### 解消済み（再実装しないこと）

- ~~フロント欠落画面~~ → payments / treasury / jobs / ops / budgets いずれも実装・テスト済み。
- ~~全銀エクスポートがモック~~ → `zengin_transfer.py` に固定長120バイトの実装済み。
- ~~フロントテスト薄い~~ → vitest 74件。権限ゲートの横断テストを含む。
- ~~MFAリカバリなし~~ → バックアップコード実装済み。

## 2-1. 壊してはいけない防御（横断テスト）

以下は「性質そのもの」を固定するテストで、**新しく追加されたコードにも自動的に効く**。
落ちたときは、テストを緩めるのではなく実装側を直すこと。走査ロジック自体の
自己検証も含んでいるため、「常に空を返す実装」に退化しても気付ける。

| テスト | 固定している性質 |
| --- | --- |
| `backend/tests/test_tenant_scope_coverage.py` | 未スコープの参照が0件／ボディの company_id 検証漏れが0件 |
| `backend/tests/test_endpoint_smoke_db.py` | 自テナントで404/500にならない／他テナントは必ず404 |
| `backend/tests/test_route_shadowing.py` | 文字列ルートがパラメータ付きルートに隠れていない |
| `backend/tests/test_migration_parity_db.py` | マイグレーションとモデル定義が一致 |
| `backend/tests/test_frontend_api_contract.py` | フロントが存在しないAPIを呼んでいない |
| `backend/tests/test_lint.py` | ruff の指摘が0件（CIの lint は `\|\| true` で握り潰される） |
| `backend/tests/test_no_inline_rate_arithmetic.py` | エンドポイントに税率・保険料率を直書きしていない |
| `backend/tests/test_frontend_api_contract.py` | 存在しないAPIを呼んでいない／概算の通知が画面に出ている |
| `frontend/app/permission-gate.test.tsx` | 権限ゼロならAPIを呼ばない（12画面） |
| `frontend/app/permission-resolve.test.tsx` | 権限が後から確定したら取得し直す（9画面） |

新しい画面・エンドポイントを追加したら、上2つのフロントテストのリストにも追加すること。

## 3. 改善案（優先度順・実行指示）

### ✅ 済 改善A: jobsの定期ディスパッチ（実装済み）
`background_jobs.py` に `job_dispatch_worker` を追加。`job_dispatch.dispatch_due_jobs`
（全社横断）で due な ScheduledJob に pending JobExecution を作成。実処理は既存の
start/complete API 経由の外部ワーカーモデルを踏襲（副作用は足さない）。

### ✅ 済 改善B: 予算管理フロント（実装済み）
`frontend/app/budgets/page.tsx`（一覧・作成・予実分析）。

### ✅ 済 改善1: 残りのフロント欠落画面
- `/budgets`（予算管理）・`/jobs`（スケジュールジョブ）・`/treasury`（資金繰り予測）・
  `/ops`（運用モニタリング）・`/payments`（支払申請）を実装済み。
- 併せて統合バグ2件を修正: ops.py の `WebhookDelivery.company_id` 参照（エンドポイント経由join）、
  payments のワークフロー欠落（一覧/承認/実行/取消エンドポイントを追加し `payment_workflow` で
  状態機械を実装）。
- 残: `/tax`(tax_forecast) の専用画面は未（税予測は単一read-onlyエンドポイント。必要なら
  budgets/treasuryパターンで追加可能）。

### 改善2 🟡 ドキュメント同期（スコープ小〜中）
- 背景: mainが追加したテーブル7件（budgets/budget_lines/bank_accounts/bank_statement_details/
  payment_requests/scheduled_jobs/job_executions）と新エンドポイントが設計書に未反映。
- 対象: `docs/OpenAPISpec.md`（§0実装対応表に budgets/payments/treasury/jobs/ops/tax を追記）、
  `docs/DataDictionary.md`・`docs/DatabaseDesign.md`（新テーブル定義）。正準はFastAPI
  自動生成 `/openapi.json` である旨を明記。
- 検証: `backend/app/api/v1/router.py`・`models.py` と記述を突き合わせて一致確認。

### ✅ 済 改善3: 全銀フォーマット（別PRで実装済み）
`app/services/zengin_transfer.py` に全銀協 総合振込フォーマット（固定長120バイト）が
実装され、`POST /payments/zengin/transfer-data` から利用できる。旧 `payment_export.py`
（pipe区切りの簡易出力）は別用途として併存。

### ✅ 済 改善4: フロントテスト拡充（実装済み）
vitest 74件。payments / ar-aging / treasury / budgets / ops / payroll の
表示・権限分岐・エラー状態に加え、権限ゲートの横断テスト2本（2-1参照）。
`CI=true npm run build` でCIでも実行される。

### 改善7 🔴 源泉所得税の法定計算（**残タスク・要スキーマ変更**）

`POST /payroll/calculate` の源泉所得税だけが概算（総支給の5%）のまま。

**社会保険料は解消済み**: `employees.birth_date` と `companies.health_insurance_rate` /
`care_insurance_rate`（migration 0030）を追加し、標準報酬月額の等級・折半端数・
介護保険の要否まで法定どおりに計算している。この時の教訓は
**「概算なのは計算方法が無いからではなく、モデルが入力を持っていなかったから」**。
源泉所得税も同じ構造なので、まず入力から埋めること。

残作業:
- `Employee` に扶養親族等の数・甲欄/乙欄区分を追加（migrationも）。
- 「給与所得の源泉徴収税額表（月額表）」を実装する。所得税法189条の
  **電子計算機等を使用する特例**を使えば、300行の表を持たずに計算できる。
  ただし別表の係数は**必ず国税庁の一次資料で確認する**こと。
- 対応したら `ESTIMATED_PAYROLL_FIELDS` を空にする。警告は自動的に消え、
  `test_estimated_fields_are_disclosed` の対になるフロントテスト
  （通知が無ければ警告を出さない）が通る設計にしてある。
- **金額を推測で埋めないこと**。誤った納付額は、概算だと明示された数字より有害。

### 改善8 🔴 消費税申告の課税区分集計（**残タスク**）

`POST /tax-returns/calculate` は課税売上・課税仕入を**売上/費用の一律80%/20%按分**で
求めており、簡易課税のみなし仕入率も事業区分によらず90%固定。申告書の数値が概算のまま。

- 本来は仕訳明細の税区分（`journal_lines.tax_rule_id`）から集計する。
  税率別（10%/8%軽減/不課税/非課税/免税）の内訳が必要。
- 簡易課税のみなし仕入率は `simplified_consumption_tax.py` に事業区分別の実装がある。
  会社または売上に事業区分を持たせて選択できるようにする。
- 現状は `estimate_notice` で概算だと明示している。対応したら
  `ESTIMATED_TAX_RETURN_FIELDS` を空にする。
- **申告書はそのまま提出されうる**。推測で数字を作らないこと。

### ✅ 済 改善5-a: MFAバックアップコード（実装済み）
`users.mfa_backup_codes`(JSONB, migration 0026)＋`mfa.py` の生成/ハッシュ/照合/消費。
**平文は保存せずSHA-256のみ**、単回使用、TOTPと同一のログインゲートでのみ受理、
再生成は現在TOTP必須、秘密鍵ローテ・MFA無効化で自動失効。
フロントは設定画面で残数表示＋再生成（平文は一度だけ表示）。
- 残: 管理者による強制リセット導線（本人がTOTPもバックアップコードも失った場合）は未実装。

### 改善5-b ⚪ 運用の堅牢化（残タスク）
- ジョブ/配信の claim/lease（PostgreSQL advisory lock）でマルチレプリカ完全排他。
- Peppol実送信はアクセスポイント契約前提のため設計メモに留める。
- `/tax`(tax_forecast) 専用画面（単一read-onlyのため優先度低）。

### ✅ 済 改善6: 債権年齢表（AR aging・実装済み）
`app/services/ar_aging.py`（純粋関数）＋`GET /reports/ar-aging`＋フロント `/ar-aging`。
実務標準区分（期日未到来/1-30/31-60/61-90/90日超）で未回収請求書を取引先別に集計。
滞留債権の回収管理と、金融商品会計基準の貸倒引当金見積り（貸倒実績率法）の基礎資料。

### （非改善）法定帳簿は既に完備 — 実装不要と確認済み
First Principles 分析で「仕訳帳・総勘定元帳・試算表が欠けているのでは」と疑ったが、
**調査の結果すべて実装済み**だった。作り直さないこと:
- 仕訳帳: `GET /journals` ＋ `GET /journals/export/csv`
- 総勘定元帳: `GET /journals/general-ledger` ＋ `/general-ledger/export`
- 試算表: `GET /reports/trial-balance` ＋ `/export`
- BS/PL/CF: `GET /reports/balance-sheet` `/income-statement` `/cash-flow` ＋ 各 `/export`
- 監査一括: `GET /audit/export`（ZIP・総勘定元帳CSV・操作証跡CSV）

### （非改善）定額法の備忘価額1円
`depreciation.py` は汎用 straight-line。**`salvage_value=1` を渡せば最終簿価1円になり
税務上の備忘価額を既にサポート**。専用パラメータ追加は冗長なので不要。

## 4. この指示書の使い方

1. 着手する改善を1つ選び、独立ブランチを切る。
2. §0共通ルールの全ゲートをグリーンにしてから PR → CI(build/test) green → main マージ。
3. 着手前に現状を再確認（本書はスナップショット）。法令計算は法条・率・端数・境界・上限を
   自分で再確認し、テストに数値例で固定する。
4. 完了した改善は本書の該当項目を「✅ 済」に更新する。
