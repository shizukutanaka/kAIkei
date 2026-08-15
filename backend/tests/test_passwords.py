"""パスワードハッシュの回帰テスト。

このモジュールは `app.core.passwords` を直接importする。`app.core.security` は jose を
importしており環境によっては読み込めないため、パスワード処理をそこから分離したことで
初めてテスト可能になった（従来 hash_password/verify_password は無テストだった）。

固定する性質:
- bcryptの72バイト制限を超える日本語パスフレーズが扱えること（日本語は1文字3バイトで
  24文字で72バイトに到達する）。
- 先頭72バイトが同一の別パスワードが区別されること（切り捨てによる認証突破の防止）。
- 旧形式($2b$)のハッシュを検証でき、再ハッシュ対象として識別できること（無停止移行）。
"""

import warnings

import pytest
from passlib.context import CryptContext

from app.core.passwords import hash_password, needs_rehash, verify_password

# 25文字 = 75バイト（UTF-8）。bcrypt単体の上限72バイトを超える。
LONG_JP_BASE = "パスワード安全性検証用長文パスフレーズ本日晴天なり"


def _legacy_bcrypt_hash(password: str) -> str:
    """移行前の実装（素のbcrypt）で作られたハッシュを再現する。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return CryptContext(schemes=["bcrypt"], deprecated="auto").hash(password)


class TestLongPassword:
    def test_japanese_passphrase_exceeding_72_bytes_roundtrips(self):
        password = LONG_JP_BASE + "AAAAAAAAAA"
        assert len(password.encode("utf-8")) > 72
        assert verify_password(password, hash_password(password)) is True

    def test_passwords_sharing_first_72_bytes_are_distinguished(self):
        """切り捨てが起きていれば別パスワードで認証が通ってしまう（回帰防止）。"""
        a = LONG_JP_BASE + "AAAAAAAAAA"
        b = LONG_JP_BASE + "BBBBBBBBBB"
        assert a.encode("utf-8")[:72] == b.encode("utf-8")[:72]
        hashed = hash_password(a)
        assert verify_password(a, hashed) is True
        assert verify_password(b, hashed) is False

    def test_very_long_ascii_password(self):
        password = "x" * 200
        assert verify_password(password, hash_password(password)) is True


class TestBasicBehaviour:
    def test_short_password_roundtrip(self):
        assert verify_password("s3cret-pw", hash_password("s3cret-pw")) is True

    def test_wrong_password_rejected(self):
        assert verify_password("wrong-pw", hash_password("s3cret-pw")) is False

    def test_hashes_are_salted(self):
        assert hash_password("same-pw") != hash_password("same-pw")

    def test_new_hashes_use_bcrypt_sha256(self):
        assert hash_password("any-pw").startswith("$bcrypt-sha256$")

    def test_new_hash_does_not_need_rehash(self):
        assert needs_rehash(hash_password("any-pw")) is False


class TestLegacyCompatibility:
    def test_legacy_bcrypt_hash_still_verifies(self):
        """既存ユーザーのハッシュを無効化しないこと（DB移行なしでの移行）。"""
        legacy = _legacy_bcrypt_hash("legacy-pw")
        assert legacy.startswith("$2")
        assert verify_password("legacy-pw", legacy) is True
        assert verify_password("other-pw", legacy) is False

    def test_legacy_hash_is_flagged_for_rehash(self):
        assert needs_rehash(_legacy_bcrypt_hash("legacy-pw")) is True

    def test_rehash_upgrades_scheme_and_still_verifies(self):
        """ログイン時の透過的な再ハッシュ相当の流れ。"""
        legacy = _legacy_bcrypt_hash("legacy-pw")
        assert needs_rehash(legacy) is True
        upgraded = hash_password("legacy-pw")  # 平文が手元にある瞬間に再ハッシュ
        assert upgraded.startswith("$bcrypt-sha256$")
        assert verify_password("legacy-pw", upgraded) is True
        assert needs_rehash(upgraded) is False


@pytest.mark.parametrize("password", ["", "a", "ぁ" * 100])
def test_edge_case_inputs_roundtrip(password):
    assert verify_password(password, hash_password(password)) is True
