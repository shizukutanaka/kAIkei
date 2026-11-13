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
├── docs/             # 設計ドキュメント
├── docker-compose.yml
├── Plan.md
└── README.md
```

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
