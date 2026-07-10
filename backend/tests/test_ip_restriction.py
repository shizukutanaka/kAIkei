from app.middleware.ip_restriction import client_ip


class TestClientIp:
    def test_prefers_forwarded_first_hop(self):
        assert client_ip("203.0.113.9, 10.0.0.1", "10.0.0.1") == "203.0.113.9"

    def test_trims_whitespace(self):
        assert client_ip("  198.51.100.2  ", None) == "198.51.100.2"

    def test_falls_back_to_client_host(self):
        assert client_ip(None, "192.168.1.5") == "192.168.1.5"
        assert client_ip("", "192.168.1.5") == "192.168.1.5"

    def test_none_when_nothing(self):
        assert client_ip(None, None) is None
