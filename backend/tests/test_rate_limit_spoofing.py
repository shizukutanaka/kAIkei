"""レート制限のIP解決に関する回帰テスト。

X-Forwarded-For を無条件に信頼していたため、リクエストごとにヘッダ値を変えるだけで
レート制限を完全に回避できた。ログインのブルートフォース防御が無効化されるため、
既定では直接接続元のIPのみを信頼する（IP許可リスト側と同じ方針）。
"""

import time

from app.middleware.rate_limit import RateLimitMiddleware


class _Client:
    def __init__(self, host):
        self.host = host


class _Request:
    def __init__(self, xff=None, host="203.0.113.9"):
        self.headers = {"x-forwarded-for": xff} if xff else {}
        self.client = _Client(host)


def _mw(**kwargs):
    return RateLimitMiddleware(app=None, max_requests=5, window_seconds=60, **kwargs)


class TestForwardedHeaderNotTrustedByDefault:
    def test_spoofed_header_does_not_create_new_bucket(self):
        """回帰: XFFを変えても同一の直接接続元として扱われること。"""
        mw = _mw()
        keys = {mw._get_client_ip(_Request(xff=f"10.0.0.{i}")) for i in range(50)}
        assert keys == {"203.0.113.9"}

    def test_rate_limit_is_reached_despite_rotating_header(self):
        mw = _mw()
        now = time.monotonic()
        for i in range(10):
            key = mw._get_client_ip(_Request(xff=f"10.0.0.{i}"))
            mw._requests[key].append(now)
        # 全て同じバケットに入り、上限5を超える
        assert len(mw._requests["203.0.113.9"]) == 10
        assert len(mw._requests) == 1

    def test_distinct_direct_clients_are_tracked_separately(self):
        mw = _mw()
        a = mw._get_client_ip(_Request(host="198.51.100.1"))
        b = mw._get_client_ip(_Request(host="198.51.100.2"))
        assert a != b

    def test_missing_client_falls_back_to_unknown(self):
        mw = _mw()
        req = _Request()
        req.client = None
        assert mw._get_client_ip(req) == "unknown"


class TestTrustProxyMode:
    """信頼できるプロキシ配下では先頭ホップを採用する（明示的に有効化した場合のみ）。"""

    def test_forwarded_header_used_when_trusted(self):
        mw = _mw(trust_proxy=True)
        assert mw._get_client_ip(_Request(xff="198.51.100.7")) == "198.51.100.7"

    def test_first_hop_is_taken(self):
        mw = _mw(trust_proxy=True)
        assert mw._get_client_ip(_Request(xff="198.51.100.7, 10.0.0.1")) == "198.51.100.7"

    def test_falls_back_to_direct_peer_without_header(self):
        mw = _mw(trust_proxy=True)
        assert mw._get_client_ip(_Request(host="203.0.113.9")) == "203.0.113.9"


class TestTrackingTableIsBounded:
    """一度きりのIPが大量に現れても追跡テーブルが無制限に増えないこと。"""

    def test_stale_keys_are_evicted_once_over_limit(self):
        mw = RateLimitMiddleware(app=None, max_requests=5, window_seconds=60, max_tracked_keys=100)
        now = time.monotonic()
        # ウィンドウを過ぎた古いキーを大量に投入する
        for i in range(500):
            mw._requests[f"192.0.2.{i}"].append(now - 3600)
        assert len(mw._requests) == 500

        mw._evict_stale(now)
        assert len(mw._requests) == 0

    def test_active_keys_are_not_evicted(self):
        mw = RateLimitMiddleware(app=None, max_requests=5, window_seconds=60, max_tracked_keys=10)
        now = time.monotonic()
        for i in range(50):
            mw._requests[f"192.0.2.{i}"].append(now)  # ウィンドウ内=アクティブ
        mw._evict_stale(now)
        # アクティブなキーは制限中の判定に必要なので残す
        assert len(mw._requests) == 50

    def test_no_eviction_below_limit(self):
        mw = RateLimitMiddleware(app=None, max_requests=5, window_seconds=60, max_tracked_keys=100)
        now = time.monotonic()
        for i in range(10):
            mw._requests[f"192.0.2.{i}"].append(now - 3600)
        mw._evict_stale(now)
        assert len(mw._requests) == 10
