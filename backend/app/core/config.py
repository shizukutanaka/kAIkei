import pathlib

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Environment ("development" / "staging" / "production")
    ENVIRONMENT: str = "development"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://kaikei:kaikei_dev@localhost:5432/kaikei"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AI Providers
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # Local LLM (Ollama / vLLM / llama.cpp / LM Studio)
    LOCAL_LLM_ENDPOINT: str = ""  # e.g. http://localhost:11434/v1
    LOCAL_LLM_MODEL: str = "llama3.2:7b"
    LOCAL_LLM_API_KEY: str = "ollama"
    LOCAL_LLM_TIMEOUT: float = 60.0

    # Task routing
    AI_PREFER_FREE: bool = True  # Prefer free/local providers for light tasks

    # S3-compatible storage
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "kaikei-documents"

    # Background jobs（Webhook配信ワーカー等の定期実行）
    BACKGROUND_JOBS_ENABLED: bool = True
    WEBHOOK_WORKER_INTERVAL_SECONDS: float = 60.0
    # スケジュールジョブの自動ディスパッチ間隔（全社横断でdue jobをpending化）。
    JOB_DISPATCH_WORKER_INTERVAL_SECONDS: float = 300.0

    # IP制限ミドルウェア: リバースプロキシ配下でのみtrueにする。
    # X-Forwarded-Forはクライアントが自由に指定できるヘッダのため、
    # 信頼できるプロキシが上書きすることが保証された構成でのみ有効化すること。
    TRUST_PROXY_HEADERS: bool = False

    # CORS: ブラウザから API を呼ぶ画面のオリジン（カンマ区切り）。
    # 本番では実際のドメインを設定すること。既定のままだと本番の画面から
    # 一切APIを呼べない（プリフライトが全て失敗する）。
    # allow_credentials=True と併用するため "*" は使えない（ブラウザが拒否する）。
    CORS_ALLOW_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # 個人用単体パッケージ: 書き出し済みの画面一式（静的ファイル群）の置き場所。
    # packaging/ の起動スクリプトが同梱の web フォルダを指定する。未設定（サーバ
    # 構成）では画面は配信しない。設定されていても実在しない場合は配信しない
    # （パス間違いで API の応答が画面に化ける事故を防ぐため）。
    WEB_DIR: str = ""

    # Application
    APP_NAME: str = "kAIkei"
    APP_VERSION: str = "0.1.0"
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def cors_allow_origins(self) -> list[str]:
        """CORS_ALLOW_ORIGINS をリストに分解する（空要素は捨てる）。"""
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

    @property
    def web_dir_path(self) -> pathlib.Path | None:
        """同梱画面の配信元ディレクトリ。配信しない場合は None。"""
        if not self.WEB_DIR:
            return None
        path = pathlib.Path(self.WEB_DIR)
        return path if path.is_dir() else None


settings = Settings()
