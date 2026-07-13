from app.core.secrets_check import DEV_JWT_SECRET, DEV_S3_CREDENTIAL, check_insecure_defaults

STRONG_SECRET = "x" * 40


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
