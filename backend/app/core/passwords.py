"""パスワードのハッシュ化・検証。

bcryptには**入力72バイトまで**という仕様上の制限がある。日本語はUTF-8で1文字3バイトの
ため、**24文字の日本語パスフレーズで72バイトに到達**する。従来の素のbcrypt設定では、
25文字以上の日本語パスワードで登録・ログインが `ValueError` となり500エラーになっていた
（bcrypt 4.x は超過分を黙って切り捨てず例外を送出する。旧実装では切り捨てられ、
先頭72バイトが同じ別パスワードでも認証が通ってしまう危険もあった）。

NIST SP 800-63B は「最低64文字の受理」と「パスワードの切り捨て禁止」を求めており、
多バイト文字を使う日本語環境では素のbcryptではこれを満たせない。

そこで passlib の `bcrypt_sha256` を採用する。これはパスワードを
**ソルト付きHMAC-SHA-256で前処理してから**bcryptに渡す方式で、
- 入力長の制限が事実上なくなる（長いパスフレーズを切り捨てない）
- 前処理がソルト付きHMACのため、単純な事前SHA-256前処理で懸念される
  password shucking（既知の平文ハッシュを使った総当たり）を避けられる

既存の `$2b$`（素のbcrypt）ハッシュも検証できるようスキーム一覧に残し、
`deprecated` 指定によりログイン成功時の再ハッシュ対象として識別する。
これによりDBマイグレーションなしで段階的に移行できる。
"""

from passlib.context import CryptContext

# 先頭が既定スキーム（新規ハッシュはbcrypt_sha256）。bcryptは検証専用として残し、
# needs_update() が True を返すようdeprecated指定する。
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"],
    deprecated=["bcrypt"],
)


def hash_password(password: str) -> str:
    """パスワードをハッシュ化する（長さ制限なし）。"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """平文パスワードとハッシュを検証する。旧形式($2b$)のハッシュも検証できる。"""
    return pwd_context.verify(plain_password, hashed_password)


def needs_rehash(hashed_password: str) -> bool:
    """ハッシュが旧スキームで、再ハッシュすべきかを返す。

    ログイン成功時（平文が手元にある瞬間）に呼び出して透過的に移行するために使う。
    """
    return pwd_context.needs_update(hashed_password)
