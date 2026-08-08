# kAIkei — 改善指示書（Opus / Sonnet セッション実行用）

> 本書は kAIkei（日本向けAI駆動統合バックオフィス/ERP）の現状監査（長所・短所）と、
> 将来の Claude（Opus/Sonnet）セッションがそのまま着手できる改善指示書である。
> 各改善は「背景 / 対象ファイル / 手順 / 検証」を備え、独立に実行可能。
> 着手前に必ず現状を再確認すること（本書はスナップショットであり、実装は進行する）。

## 0. 実行者への共通ルール（必読）

- **全テストをゲートにする**。変更後に必ず:
  - `cd backend && python -m pytest -m "not db" -q -o addopts="" -p no:cacheprovider`
  - ローカルPostgresを起動し `TEST_DATABASE_URL=postgresql+asyncpg://kaikei:kaikei_dev@127.0.0.1:5432/kaikei_test python -m pytest -m db -q -o addopts="" -p no:cacheprovider`
  - Alembicは新規スクラッチDBで `alembic upgrade head`（単一ヘッド維持）
  - frontend: `npx tsc --noEmit` / `npm run build` / `npm test`
- **1改善 = 1ブランチ = 1PR**。CI（build/test）green を確認してから main へマージ。
- コミットtrailer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` /
  `Claude-Session: <session-url>`。**モデルIDはコミット/PR/コード/コメントに含めない**。
- **日本の税・社保・労保は法令を必ず自分で再確認**（率・端数処理・境界・上限）。
  レビューは「確信できる法令ルールのみ」を数値例つきで報告・修正する。
- **jose/crypto の PanicException** で `app` 全体importは環境依存で失敗する。エンドポイント検証は
  `python -m py_compile` またはテスト経由で行う（テストは認証チェーンをimportしない）。
- 環境: docker registry 403。ローカルPostgres16バイナリを使用。**DBテストのスキーマは
  conftestの `Base.metadata.create_all`（マイグレーション未経由）で作られる**点に注意
  （＝マイグレーション欠落はテストでは表面化しない。§改善参照）。
- **model↔migration列パリティ**は `backend/tests/test_migration_model_parity.py` が保証する
  （全modelテーブルにcreate_tableがあること）。新モデル追加時はマイグレーションも必ず追加。
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

- 🟡 **フロント欠落画面**: main追加のバックエンド機能のうち **支払(/payments)・
  treasury(/treasury)・jobs(/jobs)・ops(/ops)・税予測(/tax)** にフロント画面が無い
  （予算/budgetsは実装済み）。
- 🟡 **ドキュメントdrift**: 統合後にmainが追加したテーブル7件/エンドポイントが
  `docs/OpenAPISpec.md`・`docs/DataDictionary.md`・`docs/DatabaseDesign.md` に未反映の可能性。
- ~~🟡 全銀エクスポートがモック~~ → **解消済み**（`zengin_transfer.py` に固定長120バイトの
  全銀協 総合振込フォーマットを実装済み）。
- 🟡 **フロントテスト薄い**: vitest 12件程度。ページ統合テストが少ない。
- ⚪ **マルチレプリカの完全排他なし**: FOR UPDATE SKIP LOCKED で主要窓は閉じたが、
  claim/lease方式の完全な分散ロックではない。
- ⚪ **MFAリカバリなし**: バックアップコード/管理者リセット導線が無い。
- ⚪ **Peppol実送信なし**: UBL XML生成のみ。アクセスポイント連携は未実装。
- ⚪ **JWT/S3既定値**: 本番fail-fastは実装済みだが ENVIRONMENT 設定に依存。

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

### 改善4 🟡 フロントテスト拡充（スコープ中・**残タスク**）
- 対象: `frontend/**/*.test.tsx`。@testing-library/react、`vitest.setup.ts` の cleanup 利用。
  budgets/payments/ar-aging 等の主要ページの表示/権限分岐/エラー状態をテスト。
- 現状 vitest は12件のみでページ統合テストが薄い。
- 検証: `npm test` グリーン。

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
