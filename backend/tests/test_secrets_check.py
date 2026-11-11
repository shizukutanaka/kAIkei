from app.core.secrets_check import (
    DEV_DATABASE_URL,
    DEV_JWT_SECRET,
    DEV_S3_CREDENTIAL,
    check_insecure_defaults,
)

STRONG_SECRET = "x" * 40
CUSTOM_DATABASE_URL = "postgresql+asyncpg://kaikei:prod-password@db.internal:5432/kaikei"


class TestCheckInsecureDefaults:
    def test_no_issues_with_strong_config(self):
        assert check_insecure_defaults(STRONG_SECRET, "prod-key", "prod-secret") == []

    def test_flags_default_jwt_secret(self):
        issues = check_insecure_defaults(DEV_JWT_SECRET, "prod-key", "prod-secret")
        assert len(issues) == 1
        assert "JWT_SECRET_KEY" in issues[0]

    def test_flags_short_jwt_secret(self):
        issues = check_insecure_defaults("short", "prod-key", "prod-secret")
        assert len(issues) == 1
        assert "JWT_SECRET_KEY" in issues[0]

    def test_flags_empty_jwt_secret(self):
        issues = check_insecure_defaults("", "prod-key", "prod-secret")
        assert len(issues) == 1

    def test_custom_min_length_boundary(self):
        secret = "x" * 20
        assert check_insecure_defaults(secret, "k", "s", jwt_min_length=20) == []
        assert check_insecure_defaults(secret, "k", "s", jwt_min_length=21) != []

    def test_flags_default_s3_access_key(self):
        issues = check_insecure_defaults(STRONG_SECRET, DEV_S3_CREDENTIAL, "prod-secret")
        assert len(issues) == 1
        assert "S3_ACCESS_KEY" in issues[0]

    def test_flags_default_s3_secret_key(self):
        issues = check_insecure_defaults(STRONG_SECRET, "prod-key", DEV_S3_CREDENTIAL)
        assert len(issues) == 1

    def test_flags_both_jwt_and_s3(self):
        issues = check_insecure_defaults(DEV_JWT_SECRET, DEV_S3_CREDENTIAL, DEV_S3_CREDENTIAL)
        assert len(issues) == 2

    def test_no_issues_with_custom_database_url(self):
        issues = check_insecure_defaults(
            STRONG_SECRET, "prod-key", "prod-secret", database_url=CUSTOM_DATABASE_URL
        )
        assert issues == []

    def test_flags_default_database_url(self):
        issues = check_insecure_defaults(
            STRONG_SECRET, "prod-key", "prod-secret", database_url=DEV_DATABASE_URL
        )
        assert len(issues) == 1
        assert "DATABASE_URL" in issues[0]

    def test_flags_default_database_password_on_custom_host(self):
        """接続先を変えてもパスワードが既定のままなら検出すること。"""
        url = "postgresql+asyncpg://kaikei:kaikei_dev@db.internal:5432/kaikei"
        issues = check_insecure_defaults(
            STRONG_SECRET, "prod-key", "prod-secret", database_url=url
        )
        assert len(issues) == 1
        assert "DATABASE_URL" in issues[0]

    def test_database_url_none_is_not_checked(self):
        """未指定（None）のときは従来どおり DATABASE_URL を検査しないこと。"""
        issues = check_insecure_defaults(STRONG_SECRET, "prod-key", "prod-secret", database_url=None)
        assert issues == []

    def test_flags_the_settings_default_database_url(self):
        """config の宣言デフォルトそのものが検出対象であること（定数のドリフト防止）。

        環境変数に左右されないよう、インスタンス値ではなくフィールドの
        宣言デフォルトを直接見る。
        """
        from app.core.config import Settings

        declared_default = Settings.model_fields["DATABASE_URL"].default
        issues = check_insecure_defaults(
            STRONG_SECRET, "prod-key", "prod-secret", database_url=declared_default
        )
        assert len(issues) == 1
        assert "DATABASE_URL" in issues[0]
