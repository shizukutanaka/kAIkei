"""起動時の秘密情報チェック（開発用デフォルト値の本番混入防止）。

環境変数の値だけを見て判定する純粋関数。呼び出し側（main.py）が
ENVIRONMENT に応じて「本番なら起動を拒否／それ以外は警告ログ」を判断する。
"""

DEV_JWT_SECRET = "dev-secret-key-change-in-production"
DEV_S3_CREDENTIAL = "minioadmin"
DEFAULT_MIN_JWT_SECRET_LENGTH = 32


def check_insecure_defaults(
    jwt_secret: str,
    s3_access_key: str,
    s3_secret_key: str,
    jwt_min_length: int = DEFAULT_MIN_JWT_SECRET_LENGTH,
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

    return issues
