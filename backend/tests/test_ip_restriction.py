from app.middleware.ip_restriction import client_ip, is_unauthenticated_auth_path


class TestClientIp:
    def test_defaults_to_direct_connection_ignoring_forwarded_header(self):
        # X-Forwarded-Forはクライアントが自由に指定できるため、既定(trust_proxy=False)
        # では無視し、直接接続元のIPのみを信頼する（詐称によるIP制限バイパス対策）。
        assert client_ip("203.0.113.9, 10.0.0.1", "198.51.100.7") == "198.51.100.7"

    def test_trust_proxy_true_prefers_forwarded_first_hop(self):
        assert client_ip("203.0.113.9, 10.0.0.1", "10.0.0.1", trust_proxy=True) == "203.0.113.9"

    def test_trust_proxy_true_trims_whitespace(self):
        assert client_ip("  198.51.100.2  ", None, trust_proxy=True) == "198.51.100.2"

    def test_falls_back_to_client_host_when_forwarded_empty(self):
        assert client_ip(None, "192.168.1.5", trust_proxy=True) == "192.168.1.5"
        assert client_ip("", "192.168.1.5", trust_proxy=True) == "192.168.1.5"

    def test_none_when_nothing(self):
        assert client_ip(None, None) is None
        assert client_ip(None, None, trust_proxy=True) is None


class TestIsUnauthenticatedAuthPath:
    def test_matches_login_register_refresh(self):
        assert is_unauthenticated_auth_path("/api/v1/auth/login") is True
        assert is_unauthenticated_auth_path("/api/v1/auth/register") is True
        assert is_unauthenticated_auth_path("/api/v1/auth/refresh") is True

    def test_does_not_match_authenticated_mfa_endpoints(self):
        # MFAエンドポイントはBearerトークン必須のため、IP制限の対象に含めるべき
        assert is_unauthenticated_auth_path("/api/v1/auth/mfa/status") is False
        assert is_unauthenticated_auth_path("/api/v1/auth/mfa/setup") is False
        assert is_unauthenticated_auth_path("/api/v1/auth/mfa/enable") is False
        assert is_unauthenticated_auth_path("/api/v1/auth/mfa/disable") is False

    def test_does_not_match_unrelated_paths(self):
        assert is_unauthenticated_auth_path("/api/v1/journals") is False
