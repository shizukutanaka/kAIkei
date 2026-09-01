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

## 0-1. 実際に起動して確かめること（必読）

テストが1,600件超すべて緑でも、**製品として最初の一歩が通っていなかった**。

- `POST /companies` が存在せず、会社を作る手段がAPIに無かった。ほぼ全ての機能が
  `company_id` を要求するため、登録した利用者はどの画面も使えない。
  画面の空状態は「UUIDを入力」と表示しており、入手する方法の無い値を求めていた。
- `POST /journals` が必ず500だった。応答の明細を遅延ロードしており、非同期
  セッションでは MissingGreenlet になる。仕訳を1件も登録できない（会計システムの中核）。

どちらもテストがDBへ直接INSERTしていたため検出されなかった。
**HTTP経路で「作る」テストが1件も無かった**ことが根本原因。

新しい機能を足したら、テストが緑になっただけで終わりにせず、実際に起動して
登録から辿ること。

```bash
# API
DATABASE_URL=postgresql+asyncpg://... python -m alembic upgrade head
DATABASE_URL=postgresql+asyncpg://... JWT_SECRET_KEY=dev \
  python -m uvicorn app.main:app --port 8090

# 画面
NEXT_PUBLIC_API_URL=http://127.0.0.1:8090/api/v1 npx next start -p 3100
```

登録 → ログイン → 会社作成 → 勘定科目の初期化 → 仕訳/従業員登録 → 帳票、
までを一度通すこと。この2件はそれで初めて分かった。

## 0-2. 画面をブラウザで開いて確かめること（必読）

フロントの単体テスト（vitest 84件）は**全てAPIをモックしている**。実サーバに
つないだ状態で画面を開く経路は、これをやらない限り一度も通らない。実際に
この手順でしか見つからない不具合が3件あった（CORS設定・ミドルウェア順序・
ヘルスチェックの経路違い）。

```bash
# 1) API（画面のオリジンを許可する）
cd backend && CORS_ALLOW_ORIGINS="http://localhost:3000,http://127.0.0.1:3100" \
  DATABASE_URL="postgresql+asyncpg://kaikei:kaikei_dev@localhost:5432/kaikei_dev_run" \
  uvicorn app.main:app --port 8000

# 2) 画面
cd frontend && NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000/api/v1" \
  npm run build && npx next start -p 3100
```

Playwright で全画面を巡回し、コンソールエラーと4xx/5xxを集める。**注意点**:

- **APIと画面のポートを必ず一致させる**。`CORS_ALLOW_ORIGINS` に画面のオリジンが
  無いと全部CORSエラーになり、本当の不具合が埋もれる。
- **レート制限（100req/60分あたり60秒）に自分で当たらないよう間隔を空ける**。
  35画面を一気に開くと429が出て、これも本当の不具合を隠す。
- `localhost` と `127.0.0.1` は**別オリジン**。書き方を揃える。

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
  **巻き戻しも確認済み**: 34本すべて `downgrade base` まで通り、`alembic_version` 以外
  何も残らない。直近の版は1段下げて上げ直せることも確認する（列の戻し忘れは
  `base` まで一気に落とすと表面化しないため、1段の確認が要る）。
- **非同期ワーカー**: Webhook配信＆スケジュールジョブのディスパッチを定期実行
  （`background_jobs.py`、FOR UPDATE SKIP LOCKED で二重処理防止）。
- **フロント**: Next.js 14、WCAG配慮、vitestテスト基盤。
- **全268ルートの疎通確認**: GET 128本中125本、非GET 140本中132本を、パラメータ・
  リクエスト本文を型から機械生成して実際に叩く（残り11本は外部へ取得・送信しに行く
  経路と `/health` で、**すべて理由付きで除外**）。対象から漏れた経路が出ると
  テスト自体が落ちるため、「対象外」が静かに増えない。
  — 根拠: `test_endpoint_smoke_wide_db.py` / `test_write_endpoint_smoke_db.py`。
- **ID経路のテナント照合0漏れ**: UUIDを受け取る全経路（パス・本文とも）を静的走査し、
  照合の無い経路が0件であることを固定。加えて他テナントの実在IDを使った越境テストで
  実挙動も確認（静的走査は関数単位の判定で、IDごとの追跡はしない——限界も明記済み）。
  — 根拠: `test_id_routes_are_scoped.py` / `test_path_id_tenant_isolation_db.py`。
- **パスワードはbcrypt_sha256**: bcryptの72バイト制限（日本語25文字で超過→500）を解消。
  NIST SP 800-63Bの「切り捨て禁止」に準拠し、既存ハッシュはログイン成功時に透過移行。
  — 根拠: `tests/test_passwords.py`。
- **承認の状態機械は1系統**: draft→submitted→approved→posted。どの経路で承認しても
  SoD・RBAC・承認履歴（ApprovalLog）が同一に効く。
  — 根拠: `test_journal_lifecycle_db.py`（提出を飛ばせない／履歴が残ることを固定）。
- **画面をブラウザで実際に開いて確認済み**: 35画面を実サーバに対して読み込み、
  コンソールエラーと失敗リクエストを収集する手順がある（§0-2）。
  単体テストは全てAPIをモックするため、この経路でしか見つからない不具合がある。
  — 根拠: これでCORS設定・ミドルウェア順序・ヘルスチェックの3件が見つかった。

## 2. 短所（弱み）※本書更新時点

### 🔴 最優先（利用者に誤った数字が出る／人手が必要）

- **月額表・賞与算出率表そのものが未対応**（金額の是正・概算明示は完了）。
  月次は年税額の12分の1、賞与は差分方式で、検証済みの法定部品だけから算出している。
  ただし法定の「月額表」「算出率表」そのものではないため、応答の `estimate_notice` と
  画面の警告で概算だと明示している。表の係数は国税庁の一次資料が必要（改善7参照。
  消費税の課税区分集計は改善8で対応済み）。
- **CIワークフロー本体が未修正**。`.github/workflows/*.yml` は GitHub App に
  `workflows` 権限が無く自動更新できない。現在は編集可能なファイル側の暫定措置で
  回避している（`docs/ci/backend-ci-db-tests.md` 参照）。**人手での適用が必要**で、
  適用したら暫定措置3点を削除すること。
- ~~DB統合テストがCIで走らない~~ → **CIシムで全件実行中**（`conftest.py` の
  `pytest_configure` が収集を全体に広げ、`_ci_database.py` がランナーのPostgreSQLを
  起動・プロビジョニングする）。純粋1,622件＋DB統合466件超がCIで走る。
  残るのはワークフロー本体の手動適用のみ（上の項目）。

### 🟡 中

- **画面の無いエンドポイントが多い**: 268ルート中131本にフロントの呼び出しが無い
  （前回計測の166本から減少）。内訳の上位は payroll 44・tax 20・invoices 10。
  多くは純粋な計算APIとして実装されている。「消す」か「画面を作る」かは製品判断で、
  外部利用者がいる可能性があるため独断で削除していない。
  — 計測: フロントの `apiGet/apiPost/...` 第1引数を集めてルーティングと突き合わせる
  （`test_frontend_api_contract.py` と同じ照合ロジック）。
- **ドキュメントdrift**: `docs/OpenAPISpec.md`・`docs/DataDictionary.md`・
  `docs/DatabaseDesign.md` が実装に追いついていない可能性。

### ⚪ 低

- **マルチレプリカの完全排他なし**: FOR UPDATE SKIP LOCKED で主要窓は閉じたが、
  claim/lease方式の完全な分散ロックではない。
- **Peppol実送信なし**: UBL XML生成のみ。アクセスポイント連携は未実装。
- **本番と検証のPythonバージョン差**: Dockerfile は 3.12、CIと開発環境は 3.11。
  ruff の target-version はサポート下限の py311 に合わせてある。
  **3.12 でも全件通ることは実測済み**（1,635 + 471 = 2,106件）。ただしCIは3.11
  だけなので、3.12でのみ壊れる変更は入った瞬間には気付けない。CIワークフローを
  手で直せるようになったら、両方で走らせるのが本筋（テストするのは動かす版）。
  再現手順:
  ```bash
  python3.12 -m venv /tmp/v312 && /tmp/v312/bin/pip install -r backend/requirements.txt
  /tmp/v312/bin/pip install pytest pytest-asyncio httpx
  cd backend && /tmp/v312/bin/python -m pytest -m "not db" -q
  ```

### 解消済み（再実装しないこと）

- ~~フロント欠落画面~~ → payments / treasury / jobs / ops / budgets いずれも実装・テスト済み。
- ~~全銀エクスポートがモック~~ → `zengin_transfer.py` に固定長120バイトの実装済み。
- ~~フロントテスト薄い~~ → vitest 74件。権限ゲートの横断テストを含む。
- ~~MFAリカバリなし~~ → バックアップコード実装済み。
- ~~UUIDを知っているだけで他テナントの帳簿を操作・閲覧できた~~ → 15経路を修正
  （承認・記帳の書き込み系、給与明細・賞与明細・請求書等のエクスポート系、承認履歴・
  補助科目の読み取り系）。`assert_owns()` で親を照合してから業務処理に入る。
- ~~給与・賞与の計算13本が呼べば必ず500~~ → 応答スキーマに `from_attributes` が無く
  pydanticがデータクラスを弾いていた。`*Response` 66クラスへ一括付与で種類ごと解消。
- ~~監査エクスポートが実データで500~~ → 列名誤り2連発（`journal_date`・`debit_amount`）。
  空の会社では行処理に入らず素通りしていたため、実データ入りの疎通確認に変更。
- ~~勤怠打刻が従業員IDを照合しない~~ → 存在しないIDで500、他テナントの従業員で
  登録できた。照合を追加。
- ~~承認の状態機械が2系統~~ → `/journals/{id}/approve|post` の別実装（幽霊ステータス
  `waiting`・承認履歴なし・提出飛ばし可）を削除し、`ApprovalWorkflowService` へ一本化。
- ~~パスワード72バイト制限~~ → bcrypt_sha256 へ移行（日本語25文字以上で500になっていた）。
- ~~CORS許可オリジンがベタ書き~~ → `http://localhost:3000` 固定だった。本番ドメインに
  置いた画面からは**APIを一切呼べない**（起動はするので気付きにくい）。
  `CORS_ALLOW_ORIGINS` で設定可能にし、本番でローカル既定のままなら起動時に検出する。
- ~~CORSミドルウェアが内側にあった~~ → レート制限の429・IP制限の403・冪等性の409に
  CORSヘッダが付かず、ブラウザは状態コードを読めないまま不透明なCORSエラーにしていた。
  最外側へ移動。
- ~~画面の接続状態表示が常に「エラー」~~ → 画面は `/api/v1/health` を呼ぶが
  バックエンドはルート直下の `/health` しか公開していなかった。別名を追加。
  併せて、接頭辞の外のルートまで突き合わせ対象にしていた契約テストの誤一致も修正。

## 2-1. 壊してはいけない防御（横断テスト）

以下は「性質そのもの」を固定するテストで、**新しく追加されたコードにも自動的に効く**。
落ちたときは、テストを緩めるのではなく実装側を直すこと。走査ロジック自体の
自己検証も含んでいるため、「常に空を返す実装」に退化しても気付ける。

| テスト | 固定している性質 |
| --- | --- |
| `backend/tests/test_tenant_scope_coverage.py` | 未スコープの参照が0件／ボディの company_id 検証漏れが0件 |
| `backend/tests/test_endpoint_smoke_db.py` | company_id 系GET: 自テナントで404/500にならない／他テナントは必ず404 |
| `backend/tests/test_endpoint_smoke_wide_db.py` | 残る全GET: パラメータを型から埋めて叩き5xxにならない／対象漏れが出ると落ちる |
| `backend/tests/test_write_endpoint_smoke_db.py` | 全POST/PUT/PATCH/DELETE: 本文をスキーマから生成して叩き5xxにならない |
| `backend/tests/test_id_routes_are_scoped.py` | UUIDを受け取るのにテナント照合の無い経路が0件（関数単位の判定。限界はdocstring参照） |
| `backend/tests/test_path_id_tenant_isolation_db.py` | 他テナントの実在IDでは承認・記帳・エクスポート等が必ず404（実リクエスト） |
| `backend/tests/test_response_model_eager_loading.py` | 応答に含めるリレーションを遅延ロードのままにしない（放置すると必ず500） |
| `backend/tests/test_audit_export_db.py` | 監査ZIPが実データ入りで生成でき、借方・貸方が別列に出る |
| `backend/tests/test_route_shadowing.py` | 文字列ルートがパラメータ付きルートに隠れていない |
| `backend/tests/test_migration_parity_db.py` | マイグレーションとモデル定義が一致／1段下げて上げ直せる／base まで巻き戻せて何も残らない |

| `backend/tests/test_lint.py` | ruff の指摘が0件（CIの lint は `\|\| true` で握り潰される） |
| `backend/tests/test_no_inline_rate_arithmetic.py` | エンドポイントに税率・保険料率を直書きしていない |
| `backend/tests/test_withholding_reconciles_with_year_end.py` | 月次×12＋賞与＝年税額（端数112円未満）。概算が年間で精算されること |
| `backend/tests/test_auto_journal_balances_db.py` | 自動生成の仕訳は必ず貸借一致。生成器が増えても検証を通ること |
| `backend/tests/test_frontend_api_contract.py` | フロントが存在しないAPIを呼んでいない（`/api/v1` 配下のみと突き合わせる）／概算の通知が画面に出ている |
| `backend/tests/test_cors_configuration.py` | 許可オリジンが設定可能／本番でローカル既定なら検出／CORSが最外側でエラー応答にもヘッダが付く |
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

### 改善2 ⚪ ドキュメント同期（判断: 大半は「正準の宣言」で解消済み）
- API仕様: `docs/OpenAPISpec.md` は冒頭で FastAPI 自動生成 `/openapi.json` を正準と
  宣言済み。手書きの写しを実装に追随させ続けるのは同じ情報を二重に持つことなので
  **同期作業はしない**（マスク法: 追いかける対象を削除する）。
- DBスキーマ: 正準は `models.py` で、モデル↔マイグレーションの一致は
  `test_migration_parity_db.py` が固定している。`docs/DataDictionary.md`・
  `docs/DatabaseDesign.md` の追記は読み物としての価値のみ。優先度 ⚪。

### ✅ 済 改善3: 全銀フォーマット（別PRで実装済み）
`app/services/zengin_transfer.py` に全銀協 総合振込フォーマット（固定長120バイト）が
実装され、`POST /payments/zengin/transfer-data` から利用できる。旧 `payment_export.py`
（pipe区切りの簡易出力）は別用途として併存。

### ✅ 済 改善4: フロントテスト拡充（実装済み）
vitest 74件。payments / ar-aging / treasury / budgets / ops / payroll の
表示・権限分岐・エラー状態に加え、権限ゲートの横断テスト2本（2-1参照）。
`CI=true npm run build` でCIでも実行される。

### 改善7 🟡 源泉徴収の法定表そのもの（**残タスク**・金額の是正は完了）

**是正済み**: 月次・賞与とも、検証済みの法定計算を組み立てて算出している。

- 月次 = 年税額 ÷ 12（`monthly_withholding.estimate_monthly_withholding`）
- 賞与 = 賞与を含む年税額 − 含まない年税額（`estimate_bonus_withholding`）

いずれも 給与所得控除→社会保険料控除・基礎控除・扶養控除→速算表→復興特別
所得税 という検証済みの部品だけで構成され、年末調整と定義上整合する。

**整合は実測で固定した**（`test_withholding_reconciles_with_year_end.py`）。
月次×12（賞与がある年は＋賞与）と年末調整の年税額の差は、給与のみで最大92円、
賞与ありで最大68円。いずれも端数処理（年税額の百円未満切捨＋月次の1円未満切捨×12）
だけで説明でき、**年末調整の過不足はほぼ0**になる。概算であることが許されるのは
年間で精算されるからなので、この性質が壊れたら概算ではなく誤徴収になる。
一律5%だった旧実装を再現すると許容差を大きく超えることも確認済み。

一律の率だった旧実装は、累進にならないため**両方向に**誤っていた:

| | 旧 | 妥当な水準 |
| --- | --- | --- |
| 月次: 月給40万・社保6万 | 20,000円(5%) | 約10,400円 |
| 月次: 月給8万（年収96万） | 4,000円 | **0円** |
| 賞与: 月給20万・賞与40万 | 40,840円(10.21%) | 11,231円 |
| 賞与: 月給100万・賞与200万 | 204,200円 | 約447,000円（不足） |

**社会保険料も是正済み**（等級・折半端数・介護保険の要否・標準賞与額の上限）。

残作業は**表そのもの**だけ:
- 「給与所得の源泉徴収税額表（月額表）」と「賞与に対する源泉徴収税額の算出率表」。
  所得税法189条の電子計算機特例を使えば300行の表を持たずに済む。
- 甲欄/乙欄の区分は `Employee` に未保持。
- 別表の係数は**必ず国税庁の一次資料で確認する**こと。推測で埋めないこと。
  誤った納付額は、概算だと明示された数字より有害。
- 対応したら `ESTIMATED_PAYROLL_FIELDS` / `ESTIMATED_BONUS_FIELDS` を空にする。
  警告は自動的に消える（通知が無ければ出さないことをフロントのテストで固定済み）。

### ✅ 済 改善8: 消費税申告の課税区分集計（実装済み）

`POST /tax-returns/calculate` は課税売上・課税仕入を売上・費用の一律80%/20%で
按分しており、実際の取引と無関係な数値が申告書に載っていた。簡易課税の
みなし仕入率も事業区分によらず90%固定だった。

`consumption_tax_classification.py` で `journal_lines.tax_rule_id` から
税区分別（課税/輸出免税/非課税/不課税）に集計するようにした。仮受消費税は
税率ごとに計算する（軽減税率8%の混在で一律10%を掛けると取りすぎる）。
簡易課税は事業区分ごとのみなし仕入率を使う。

**この件の教訓**: 「実装量が多い」と「データが無い」は違う。必要なデータは
最初から `journal_lines.tax_rule_id` にあり、外部の一次資料が要る税額表とは
事情が異なっていた。着手前に「本当に何が足りないのか」を確認すること。

税区分が未設定の明細は課税・非課税のいずれにも倒さず、件数と金額を警告に出す。
全明細が分類済みなら警告は消える。

### ✅ 済 改善9: 承認経路の一本化（実装済み）
`/journals/{id}/approve|post` にあった別実装は、`waiting` という他のどこにも存在しない
ステータスを受け付け、**承認履歴（ApprovalLog）を書かず**、提出を飛ばして
draft→approved できた。`ApprovalWorkflowService` への委譲に置き換え、
`JournalService.approve_journal/post_journal` は削除。どの経路でも
draft→submitted→approved→posted・SoD・RBAC・履歴記録が同一に効く。
根拠: `test_journal_lifecycle_db.py::test_approving_via_journals_router_leaves_an_audit_trail` /
`test_approval_cannot_skip_submission`。

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

## 3-1. 洗い出しの方法（次に読む人へ）

本書の項目は、以下の2つを機械的に当てて洗い出している。同じ手順を繰り返せば
同じ質の指摘が出る。**思いつきで探さないこと。**

### ソクラテス問答法: 各主張に「それはどうやって分かるのか」を問う

主張を額面どおり受け取らず、根拠の実在を確かめる。実際にこの問いで見つかったもの:

| 主張 | 問い | 実際の答え |
| --- | --- | --- |
| 「エンドポイントは疎通確認済み」 | 何本のうち何本か | **128本中28本だけ**。残り100本は未確認だった |
| 「監査エクスポートを直した」 | 直った状態を何が示すか | 確認に使った会社に仕訳が0件で、行処理に入っていなかった |
| 「テナント分離はテスト済み」 | どのIDで確かめたか | 存在しないUUIDだけ。他人の**実在**IDでは越境できた |
| 「1,600件のテストが緑」 | 何を通っていないか | HTTP経路を通らず、仕訳作成が全て500でも緑だった |
| 「CIでDBテストが走らない」 | 今も走らないのか | シム導入済みで466件走る。本書の記述が古かった |

**要点**: 「テストがある」は「確認できている」ではない。数を数え、範囲を言い、
欠陥を仕込んで落ちることを確かめる。落ちなければそのテストは何も守っていない。

### イーロン・マスク思考法: 要件を疑う→削除→簡素化→自動化

順番が重要。**存在しなくてよいものを速くしても意味がない。**

| 段階 | 本書での適用例 |
| --- | --- |
| 要件を疑う | 「月額表は必須か」→ 所得税法189条の電子計算機特例で300行の表は不要 |
| 削除 | 承認の別実装（改善9）・追いかけるだけのAPI仕様書（改善2）を消す |
| 簡素化 | 13箇所の個別修正ではなく `*Response` へ `from_attributes` を一括付与 |
| 自動化 | 個別テストを書かず、ルーティングから対象を生成して全経路を叩く |

**要点**: 例外リストを作って回るのは、直したことにならない。例外が増えていく形に
したら負け。「対象から漏れたら落ちる」テストにしておくと、漏れが自動で表面化する。

### 自己検証: 走査は必ず「欠陥を仕込んで」確かめる

本書の防御（2-1）はすべて、**わざと壊して落ちることを確認してから**追加している。
確認していない走査は「常に空を返す実装」に退化しても誰も気付かない。

## 4. この指示書の使い方

1. 着手する改善を1つ選び、独立ブランチを切る。
2. §0共通ルールの全ゲートをグリーンにしてから PR → CI(build/test) green → main マージ。
3. 着手前に現状を再確認（本書はスナップショット）。法令計算は法条・率・端数・境界・上限を
   自分で再確認し、テストに数値例で固定する。
4. 完了した改善は本書の該当項目を「✅ 済」に更新する。
