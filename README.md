# kAIkei — 統合バックオフィスプラットフォーム

AI駆動の日本向け統合ERPシステム。会計・給与・税務・固定資産・支払を統合し、AI仕訳推論・電帳法対応・e-Gov連携を提供する。

## 技術スタック

- **Backend**: Python 3.12+ / FastAPI / SQLAlchemy 2.0 / Alembic
- **Frontend**: Next.js 14 (App Router) / React 18 / TailwindCSS / shadcn/ui
- **Database**: PostgreSQL 16 (UUID主キー・RLS・JSONB・WALアーカイブ)
- **AI**: OpenAI GPT-4o / Anthropic Claude (デュアルプロバイダー)
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
