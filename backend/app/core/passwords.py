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


_DUMMY_PASSWORD = "dummy-password-for-constant-time-login"
# ユーザー不在時の空打ち用ハッシュ。実ハッシュと同一スキーム・同一コスト(r=12)のため
# 検証時間もほぼ同じになる。秘密情報ではない（タイミングを揃える目的のみ）。
_DUMMY_HASH = "$bcrypt-sha256$v=2,t=2b,r=12$JfNOLv.GPx0fXJQ0MLm4Ve$0sHlnbQagqualdUkIAMXHw4/20q6OkO"


def verify_dummy_password() -> None:
    """ユーザーが存在しない場合でもパスワード検証と同等の計算を行う。

    `if not user or not verify_password(...)` のように短絡すると、
    **存在しないメールアドレスでは応答が即座に返る**一方、存在するメールでは
    bcryptの計算時間（実測で約250ms）がかかる。この差は容易に観測でき、
    攻撃者は登録済みメールアドレスを列挙できてしまう
    （CWE-208 Observable Timing Discrepancy / OWASP Authentication Cheat Sheet は
    認証応答を内容だけでなく**時間的にも**区別できないようにすることを求めている）。

    ユーザー不在時に本関数を呼ぶことで、両者の応答時間を揃える。
    """
    try:
        pwd_context.verify(_DUMMY_PASSWORD, _DUMMY_HASH)
    except ValueError:
        # ダミーハッシュが解釈できない場合でも、実際のハッシュ化と同等の計算を行って
        # 時間差を残さない（認証結果には影響しない）。
        pwd_context.hash(_DUMMY_PASSWORD)


def needs_rehash(hashed_password: str) -> bool:
    """ハッシュが旧スキームで、再ハッシュすべきかを返す。

    ログイン成功時（平文が手元にある瞬間）に呼び出して透過的に移行するために使う。
    """
    return pwd_context.needs_update(hashed_password)
