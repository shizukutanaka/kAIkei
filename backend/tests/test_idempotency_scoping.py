"""冪等キーの名前空間分離に関する回帰テスト。

保存キーが冪等キー文字列だけだったため、別テナントが同じ冪等キーを使うと
互いのキャッシュに当たっていた（本文一致ならレスポンス本文が漏れ、不一致なら
409で相手の正当なリクエストを妨害できる）。呼び出し元ごとに分離する。

`build_scoped_key` は純粋関数なので、jose を読み込む認証チェーンに依存せずテストできる。
"""

from app.middleware.idempotency import build_scoped_key

KEY = "order-2026-0001"  # 意味のある値はテナント間で衝突しやすい


class TestCallerIsolation:
    def test_different_users_get_different_keys(self):
        a = build_scoped_key(KEY, "user-a", None)
        b = build_scoped_key(KEY, "user-b", None)
        assert a != b

    def test_same_user_same_key_is_stable(self):
        """同一利用者の再送は同じ保存キーになる（冪等性そのものは維持する）。"""
        assert build_scoped_key(KEY, "user-a", None) == build_scoped_key(KEY, "user-a", None)

    def test_authenticated_and_anonymous_are_separated(self):
        assert build_scoped_key(KEY, "user-a", "203.0.113.9") != build_scoped_key(
            KEY, None, "203.0.113.9"
        )

    def test_anonymous_callers_separated_by_client_ip(self):
        a = build_scoped_key(KEY, None, "203.0.113.9")
        b = build_scoped_key(KEY, None, "198.51.100.4")
        assert a != b

    def test_anonymous_without_ip_falls_back_to_unknown(self):
        assert build_scoped_key(KEY, None, None).startswith("anon:unknown|")

    def test_user_scope_does_not_depend_on_ip(self):
        """認証済みなら接続元IPが変わっても同じ保存キー（モバイル回線切替等で壊れない）。"""
        assert build_scoped_key(KEY, "user-a", "203.0.113.9") == build_scoped_key(
            KEY, "user-a", "198.51.100.4"
        )

    def test_key_is_preserved_in_scoped_form(self):
        scoped = build_scoped_key(KEY, "user-a", None)
        assert scoped.endswith(f"|{KEY}")
        assert "user-a" in scoped


class TestCrossTenantCollisionRegression:
    def test_two_tenants_using_identical_key_do_not_collide(self):
        """回帰: 同一の冪等キーでも別利用者なら別エントリになること。"""
        tenant_a_user = "11111111-1111-1111-1111-111111111111"
        tenant_b_user = "22222222-2222-2222-2222-222222222222"

        stored: dict[str, str] = {}
        stored[build_scoped_key(KEY, tenant_a_user, None)] = "tenant-a-response"
        stored[build_scoped_key(KEY, tenant_b_user, None)] = "tenant-b-response"

        # 分離前は1エントリに上書きされ、片方が相手の応答を受け取っていた。
        assert len(stored) == 2
        assert stored[build_scoped_key(KEY, tenant_a_user, None)] == "tenant-a-response"
        assert stored[build_scoped_key(KEY, tenant_b_user, None)] == "tenant-b-response"
