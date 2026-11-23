# kAIkei — 統合バックオフィスプラットフォーム

AI駆動の日本向け統合ERPシステム。会計・給与・税務・固定資産・支払を統合し、AI仕訳推論・電帳法対応・e-Gov連携を提供する。

## 技術スタック

- **Backend**: Python 3.12+ / FastAPI / SQLAlchemy 2.0 / Alembic
- **Frontend**: Next.js 14 (App Router) / React 18 / TailwindCSS / shadcn/ui
- **Database**: PostgreSQL 16 (UUID主キー・RLS・JSONB・WALアーカイブ)
- **AI**: OpenAI GPT-4o / Anthropic Claude (デュアルプロバイダー) ＋ ローカルLLM（Ollama / vLLM / llama.cpp / LM Studio。`AI_PREFER_FREE=true` で無料／ローカル優先のタスクルーティング）
- **Infrastructure**: Docker / Docker Compose / Redis / S3互換ストレージ

## プロジェクト構成

```
kAIkei/
├── backend/          # FastAPI バックエンド
├── frontend/         # Next.js フロントエンド
├── packaging/        # 個人用単体パッケージ（Windows）の組み立て
├── docs/             # 設計ドキュメント
├── docker-compose.yml
├── Plan.md
└── README.md
```

## 中核フロー: 銀行明細から仕訳へ

kAIkei の中心は「銀行の入出金データを仕訳に変換し、会計ソフトへ渡す」ことです。

1. **取り込み**（銀行明細・自動消込の画面）: 銀行・カード会社のCSVをそのまま
   アップロードします。文字コード（UTF-8 / Shift_JIS）は自動判定、日付表記
   （西暦の主要形式・和暦）や銀行ごとの列名の違いは吸収します。列名が想定と
   違う場合は、画面の「列の対応付け」で自分のファイルに合わせて指定できます。
   読み飛ばした行は、理由と行番号を必ず表示します（黙って捨てることはしません）。
2. **仕訳化**: 未消込の明細ごとに「仕訳化」を押すと、過去の確定仕訳から学習した
   相手科目の候補（信頼度つき）が出ます。人が確認・修正してドラフトを作成し、
   確定（転記）した仕訳は次の学習データになります（修正が学習に返ります）。
   学習は自社データだけ・外部送信なし・同じ入力には同じ候補を返します。
3. **書き出し**（仕訳一覧の画面）: 汎用CSV（freee / MoneyForward 互換形式）に
   加え、弥生会計の取り込み形式（25項目・Shift_JIS）でも出力できます。
   税区分は、仕訳に税ルールが付いていればその名称、無ければ「対象外」で
   出力します（弥生側で科目・税区分の対応付けが必要な場合はマッチング画面で
   指定できます）。

## 個人用単体モード（標準の使い方）

個人で使う場合は、データベースサーバも Docker も要りません。データは
SQLite のファイル1つ（`data/kaikei.db`）に収まり、バックアップは
ファイルのコピーで済みます。

- **Windows パッケージ**: `python3 packaging/build_package.py` で
  `dist/kaikei-windows.zip` を組み立てます（Python 本体と依存を同梱。
  配布・公開は金融ゲートのため行いません）。展開して
  `START-KAIKEI.bat` をダブルクリックすると、ポートの空きを確認して
  ブラウザで画面が開きます。初回だけアカウント作成の画面が出ます。
  手順の詳細はパッケージ同梱の `README.txt` を参照してください。
- **仕組み**: 起動時に `DATABASE_URL` が SQLite を指していれば単体モードに
  なります（スキーマは起動時に自動作成、`WEB_DIR` があれば画面も同じ
  アプリから配信）。PostgreSQL を指す従来構成では単体モードの処理は
  一切走りません。
- **承認まわり**: 単体モードでは仕訳の承認・転記を作成者本人でも実行
  できます（職務分掌の確認だけを単体モードで外す。承認権限の確認は
  従来どおり）。通常モードの職務分掌は変わりません。

## クイックスタート

以下の手順は**ローカル開発環境用**です（`ENVIRONMENT` 既定 = `development`）。

```bash
# 開発環境起動
docker-compose up -d

# バックエンド
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# フロントエンド
cd frontend
npm install
npm run dev
```

### 環境変数と本番起動時の fail-fast

設定は環境変数で与えます（`backend/.env.example` に全項目と説明があります）。

```bash
cp backend/.env.example backend/.env   # 値を環境に合わせて編集
```

起動時には秘密情報のチェックが走ります（`backend/app/main.py` の `validate_secrets` /
`backend/app/core/secrets_check.py`）:

- **`ENVIRONMENT=production` の場合**: 開発用デフォルト値のままの項目があると、
  `RuntimeError: Refusing to start in production with insecure configuration: ...`
  で**起動を拒否**します。本番では少なくとも以下を必ず差し替えてください。
  - `DATABASE_URL`（パスワードが開発用デフォルト `kaikei_dev` のままだと検出されます。未設定の場合も既定値が使われるため検出対象です）
  - `JWT_SECRET_KEY`（未設定・開発用デフォルト・32文字未満のいずれも不可。`openssl rand -hex 32` 等で生成）
  - `S3_ACCESS_KEY` / `S3_SECRET_KEY`（開発用デフォルト `minioadmin` 不可）
  - CORS の許可オリジン（ローカル開発用オリジンや `*` は不可）
- **`ENVIRONMENT` が `production` 以外の場合**（既定の `development` を含む）:
  同じ検出は警告ログのみで、開発用デフォルト値のまま起動できます。

`docker-compose.yml` は開発用デフォルト値のまま使う構成です。compose の値を流用して
`ENVIRONMENT=production` にすると上記のとおり起動に失敗するので、本番用の値は
別途環境変数で注入してください。

## テスト

```bash
cd backend

# 純粋ロジックテスト（DB不要）
pytest tests/ -m "not db"

# DB統合テスト（PostgreSQL 16が必要。未設定時は自動スキップ）
TEST_DATABASE_URL=postgresql+asyncpg://kaikei:kaikei_dev@localhost:5432/kaikei_test \
  pytest tests/ -m db
```

フロントエンドは `npx tsc --noEmit` と `npm run build` で検証する。

## ドキュメント

- [Plan.md](./Plan.md) — 開発計画書
- [docs/DatabaseDesign.md](./docs/DatabaseDesign.md) — DB設計書
- [docs/OpenAPISpec.md](./docs/OpenAPISpec.md) — API仕様書
- [docs/DataDictionary.md](./docs/DataDictionary.md) — データ辞書
- [docs/ScreenSpec.md](./docs/ScreenSpec.md) — 画面仕様書
- [docs/BPMNspec.md](./docs/BPMNspec.md) — 業務フロー仕様書
- [docs/TestCatalog.md](./docs/TestCatalog.md) — テストカタログ
- [docs/LegalRuleCatalog.md](./docs/LegalRuleCatalog.md) — 法令ルールカタログ
- [docs/MigrationSpec.md](./docs/MigrationSpec.md) — 移行仕様書
- [docs/IntegrationSpec.md](./docs/IntegrationSpec.md) — 外部連携仕様書
- [docs/ADR.md](./docs/ADR.md) — アーキテクチャ決定記録
- [docs/OpsDesign.md](./docs/OpsDesign.md) — 運用設計書
- [docs/ImprovementGuide.md](./docs/ImprovementGuide.md) — 改善指示書（長所・短所・改善案／Claude実行用）
