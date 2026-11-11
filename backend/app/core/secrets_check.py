"""起動時の秘密情報チェック（開発用デフォルト値の本番混入防止）。

環境変数の値だけを見て判定する純粋関数。呼び出し側（main.py）が
ENVIRONMENT に応じて「本番なら起動を拒否／それ以外は警告ログ」を判断する。
"""

from urllib.parse import urlparse

DEV_JWT_SECRET = "dev-secret-key-change-in-production"
DEV_S3_CREDENTIAL = "minioadmin"
DEV_DATABASE_URL = "postgresql+asyncpg://kaikei:kaikei_dev@localhost:5432/kaikei"
DEV_DATABASE_PASSWORD = "kaikei_dev"
DEFAULT_MIN_JWT_SECRET_LENGTH = 32


def check_insecure_defaults(
    jwt_secret: str,
    s3_access_key: str,
    s3_secret_key: str,
    jwt_min_length: int = DEFAULT_MIN_JWT_SECRET_LENGTH,
    cors_origins: list[str] | None = None,
    database_url: str | None = None,
) -> list[str]:
    """開発用デフォルト値・脆弱な設定を検出し、問題点のリストを返す。

    問題がなければ空リスト。
    """
    issues: list[str] = []

    if not jwt_secret or jwt_secret == DEV_JWT_SECRET or len(jwt_secret) < jwt_min_length:
        issues.append(
            f"JWT_SECRET_KEY is unset, the development default, or shorter than "
            f"{jwt_min_length} characters"
        )

    if s3_access_key == DEV_S3_CREDENTIAL or s3_secret_key == DEV_S3_CREDENTIAL:
        issues.append("S3_ACCESS_KEY/S3_SECRET_KEY are using the default MinIO development credentials")

    issues.extend(check_cors_origins(cors_origins))
    issues.extend(check_database_url(database_url))

    return issues


def check_database_url(database_url: str | None) -> list[str]:
    """DATABASE_URL が開発用デフォルト認証情報のままか検査する。

    未設定だと config の既定値（パスワード `kaikei_dev`）が使われるため、
    JWT/S3 と同様に「出荷デフォルトのまま本番稼働する」事故が起こりうる。
    URL 全体が既定値と一致する場合だけでなく、接続先を変えてもパスワードが
    既定のままの場合も検出する。
    """
    if database_url is None:
        return []

    if database_url == DEV_DATABASE_URL or _url_password(database_url) == DEV_DATABASE_PASSWORD:
        return ["DATABASE_URL is unset or still uses the development default credentials"]

    return []


def _url_password(url: str) -> str | None:
    """URL からパスワードを取り出す。解析できない・含まれなければ None。"""
    try:
        return urlparse(url).password
    except ValueError:
        return None


def check_cors_origins(origins: list[str] | None) -> list[str]:
    """CORS の許可オリジンを検査する。

    本番でローカル開発用のオリジンのままだと、画面からAPIを呼ぶ全ての
    リクエストがプリフライトで失敗する（起動はするので気付きにくい）。
    また `*` は `allow_credentials=True` と併用できず、ブラウザが拒否する。
    """
    if origins is None:
        return []

    issues: list[str] = []
    if not origins:
        issues.append("CORS_ALLOW_ORIGINS is empty; the browser cannot call the API")
        return issues

    if "*" in origins:
        issues.append(
            "CORS_ALLOW_ORIGINS contains '*', which browsers reject when credentials are sent"
        )

    if all(_is_local(o) for o in origins):
        issues.append(
            "CORS_ALLOW_ORIGINS only allows local development origins "
            f"({', '.join(origins)}); the production frontend would be blocked"
        )

    return issues


def _is_local(origin: str) -> bool:
    lowered = origin.lower()
    return any(host in lowered for host in ("localhost", "127.0.0.1", "[::1]"))
