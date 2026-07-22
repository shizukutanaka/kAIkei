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
- 🟡 **全銀エクスポートがモック**: `payment_export.py` は pipe区切り・UTF-8。
  実際の全銀は Shift-JIS・固定長120バイト・整数円・ゼロ埋め。
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

### 改善1 🟡 残りのフロント欠落画面（スコープ中〜大）
- 背景: /payments・/treasury・/jobs・/ops・/tax(tax_forecast) にUIが無い。
- 対象: `frontend/app/<feature>/page.tsx` を **budgets/documents/webhooks ページのパターン**で新設。
  `lib/api.ts`（apiGet/apiPost/apiDelete）、company-context、RBAC権限ガード、SkeletonTable、
  error/notice を再利用。バックエンドのスキーマは
  `python -m py_compile` 不要、`backend/app/schemas/schemas.py` と各endpointを読んで型を合わせる。
  サイドバーは `frontend/components/sidebar.tsx` の navSections に追加。
- 検証: `tsc --noEmit` / `npm run build` / vitest。

### 改善2 🟡 ドキュメント同期（スコープ小〜中）
- 背景: mainが追加したテーブル7件（budgets/budget_lines/bank_accounts/bank_statement_details/
  payment_requests/scheduled_jobs/job_executions）と新エンドポイントが設計書に未反映。
- 対象: `docs/OpenAPISpec.md`（§0実装対応表に budgets/payments/treasury/jobs/ops/tax を追記）、
  `docs/DataDictionary.md`・`docs/DatabaseDesign.md`（新テーブル定義）。正準はFastAPI
  自動生成 `/openapi.json` である旨を明記。
- 検証: `backend/app/api/v1/router.py`・`models.py` と記述を突き合わせて一致確認。

### 改善3 🟡 全銀フォーマットの実装（スコープ中・規格準拠）
- 背景: `app/services/payment_export.py` はモック。実全銀は Shift-JIS・固定長・整数円・ゼロ埋め、
  ヘッダ/データ/トレーラ/エンド の4レコード。
- 対象: 同ファイル。既存 `_fit` を活用し各フィールド幅・右詰めゼロ埋め・半角カナを実装。
  破壊的変更のため、旧mock出力に依存するテストは新仕様に合わせて書き換える。
- 検証: レコード種別・バイト長・文字コード・フィールド位置の純粋テスト。

### 改善4 🟡 フロントテスト拡充（スコープ中）
- 対象: `frontend/**/*.test.tsx`。@testing-library/react、`vitest.setup.ts` の cleanup 利用。
  budgets等の主要ページの表示/権限分岐/エラー状態をテスト。
- 検証: `npm test` グリーン。

### 改善5 ⚪ セキュリティ/運用の堅牢化（スコープ小〜中）
- MFAバックアップコード（ハッシュ保存＋一度限り消費）＋管理者リセット導線。
- ジョブ/配信の claim/lease（PostgreSQL advisory lock）でマルチレプリカ完全排他。
- Peppol実送信はアクセスポイント契約前提のため設計メモに留める。

### （非改善）定額法の備忘価額1円
`depreciation.py` は汎用 straight-line。**`salvage_value=1` を渡せば最終簿価1円になり
税務上の備忘価額を既にサポート**。専用パラメータ追加は冗長なので不要。

## 4. この指示書の使い方

1. 着手する改善を1つ選び、独立ブランチを切る。
2. §0共通ルールの全ゲートをグリーンにしてから PR → CI(build/test) green → main マージ。
3. 着手前に現状を再確認（本書はスナップショット）。法令計算は法条・率・端数・境界・上限を
   自分で再確認し、テストに数値例で固定する。
4. 完了した改善は本書の該当項目を「✅ 済」に更新する。
