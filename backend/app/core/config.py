from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

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

    # Application
    APP_NAME: str = "kAIkei"
    APP_VERSION: str = "0.1.0"
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
