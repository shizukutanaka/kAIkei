"""MFA（TOTP: RFC 6238）の実装。

外部依存なし（hmac/hashlib/base64/secretsのみ）。TOTPコード生成・検証・
otpauth URI組み立ては純粋関数で単体テスト可能。DB操作（設定・有効化・無効化）は
非同期関数として分離する。
"""

import base64
import hashlib
import hmac
import secrets as secrets_module
import struct
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_PERIOD_SECONDS = 30
DEFAULT_DIGITS = 6


class MfaReauthRequired(Exception):
    """MFA有効時の秘密鍵再発行には現在のTOTPコードが必要（未提示/不正な場合に送出）。"""


def generate_totp_secret() -> str:
    """160bitのランダム秘密鍵をbase32文字列（パディングなし）で生成する。"""
    return base64.b32encode(secrets_module.token_bytes(20)).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    normalized = secret.strip().replace(" ", "").upper()
    padded = normalized + "=" * (-len(normalized) % 8)
    return base64.b32decode(padded)


def _hotp(key: bytes, counter: int, digits: int) -> str:
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return str(binary % (10**digits)).zfill(digits)


def totp_code(
    secret: str,
    timestamp: int,
    period: int = DEFAULT_PERIOD_SECONDS,
    digits: int = DEFAULT_DIGITS,
) -> str:
    """指定時刻のTOTPコードを計算する（RFC 6238, HMAC-SHA1）。"""
    return _hotp(_decode_secret(secret), int(timestamp) // period, digits)


def find_matching_step(
    secret: str,
    code: str,
    timestamp: int,
    window: int = 1,
    period: int = DEFAULT_PERIOD_SECONDS,
    digits: int = DEFAULT_DIGITS,
) -> int | None:
    """コードに一致する時間ステップ（カウンタ値）を返す。一致しなければNone。

    時計ずれ許容として前後windowステップを受理する。
    """
    cleaned = code.strip().replace(" ", "")
    if not cleaned.isdigit() or len(cleaned) != digits:
        return None
    try:
        key = _decode_secret(secret)
    except (ValueError, TypeError):
        return None
    counter = int(timestamp) // period
    for offset in range(-window, window + 1):
        candidate = counter + offset
        if hmac.compare_digest(_hotp(key, candidate, digits), cleaned):
            return candidate
    return None


def verify_totp(
    secret: str,
    code: str,
    timestamp: int,
    window: int = 1,
    period: int = DEFAULT_PERIOD_SECONDS,
    digits: int = DEFAULT_DIGITS,
) -> bool:
    """TOTPコードを検証する（リプレイ判定なしの単発検証）。"""
    return find_matching_step(secret, code, timestamp, window, period, digits) is not None


def check_and_consume_step(
    secret: str,
    code: str,
    timestamp: int,
    last_used_step: int | None,
    window: int = 1,
    period: int = DEFAULT_PERIOD_SECONDS,
    digits: int = DEFAULT_DIGITS,
) -> int | None:
    """コードを検証し、直近使用済みステップより新しい場合のみ新ステップを返す。

    同一コードの再送（リプレイ）を防ぐため、`last_used_step` 以下のステップに
    一致した場合は不正として None を返す。
    """
    step = find_matching_step(secret, code, timestamp, window, period, digits)
    if step is None:
        return None
    if last_used_step is not None and step <= last_used_step:
        return None
    return step


def build_otpauth_uri(secret: str, account_name: str, issuer: str = "kAIkei") -> str:
    """認証アプリ登録用の otpauth:// URI を組み立てる。"""
    label = f"{quote(issuer)}:{quote(account_name)}"
    return (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits={DEFAULT_DIGITS}"
        f"&period={DEFAULT_PERIOD_SECONDS}"
    )


async def _get_user(db: AsyncSession, user_id: UUID):
    from app.models.models import User

    result = await db.execute(select(User).where(User.user_id == user_id))
    return result.scalar_one_or_none()


async def verify_and_consume_totp(db: AsyncSession, user, code: str, timestamp: int) -> bool:
    """ユーザーの現在の秘密鍵に対しコードを検証し、リプレイでなければ使用済み
    ステップを更新する（呼び出し側でdb.flush/commitが必要な変更を`user`に加える）。
    """
    if not user.mfa_secret:
        return False
    step = check_and_consume_step(user.mfa_secret, code, timestamp, user.mfa_last_used_step)
    if step is None:
        return False
    user.mfa_last_used_step = step
    await db.flush()
    return True


async def setup_mfa(
    db: AsyncSession,
    user_id: UUID,
    current_code: str | None = None,
    timestamp: int | None = None,
) -> tuple[str, str] | None:
    """新しい秘密鍵を発行して保存する（この時点では未有効）。

    MFAが既に有効なアカウントに対しては、現在のTOTPコード（current_code /
    timestamp）の検証を必須とする。これがないと、盗まれたアクセストークン
    だけで（TOTPコードを一切知らずに）秘密鍵を差し替えてMFAを実質的に無効化
    できてしまう（/mfa/disable が要求する現在コード検証を素通りするバイパス）。

    Returns:
        (secret, otpauth_uri)。ユーザーが見つからなければ None。

    Raises:
        MfaReauthRequired: MFA有効時に現在のコードが未提示または不正な場合。
    """
    user = await _get_user(db, user_id)
    if user is None:
        return None
    if user.mfa_enabled:
        if timestamp is None or not current_code or not await verify_and_consume_totp(
            db, user, current_code, timestamp
        ):
            raise MfaReauthRequired()
    secret = generate_totp_secret()
    user.mfa_secret = secret
    user.mfa_enabled = False
    user.mfa_last_used_step = None
    user.mfa_backup_codes = None  # 旧秘密鍵向けのバックアップコードを無効化
    await db.flush()
    return secret, build_otpauth_uri(secret, user.email)


async def enable_mfa(db: AsyncSession, user_id: UUID, code: str, timestamp: int) -> bool:
    """setup済みの秘密鍵に対しコードを検証し、MFAを有効化する。"""
    user = await _get_user(db, user_id)
    if user is None or not user.mfa_secret:
        return False
    if not await verify_and_consume_totp(db, user, code, timestamp):
        return False
    user.mfa_enabled = True
    await db.flush()
    return True


async def disable_mfa(db: AsyncSession, user_id: UUID, code: str, timestamp: int) -> bool:
    """コードを検証してMFAを無効化し、秘密鍵を破棄する。"""
    user = await _get_user(db, user_id)
    if user is None or not user.mfa_enabled or not user.mfa_secret:
        return False
    if not await verify_and_consume_totp(db, user, code, timestamp):
        return False
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_last_used_step = None
    user.mfa_backup_codes = None
    await db.flush()
    return True


# --- MFAバックアップコード（TOTP認証器を紛失した際の復旧手段） -----------------

DEFAULT_BACKUP_CODE_COUNT = 10


def _normalize_backup_code(code: str) -> str:
    """入力コードを正規化する（空白/ハイフン除去・大文字化）。表示整形を吸収する。"""
    return "".join(ch for ch in code.strip().upper() if ch.isalnum())


def hash_backup_code(code: str) -> str:
    """バックアップコードのSHA-256ハッシュ（16進）。コードは高エントロピー乱数のため
    ソルト不要（APIキーと同様）。正規化してからハッシュする。"""
    return hashlib.sha256(_normalize_backup_code(code).encode("ascii")).hexdigest()


def generate_backup_codes(count: int = DEFAULT_BACKUP_CODE_COUNT) -> list[str]:
    """人が書き写せる高エントロピーのバックアップコードを生成する（表示は once）。

    各コードは Crockford風base32の10文字（約50bit）。表示整形のため中央にハイフンを入れる。
    """
    alphabet = "ABCDEFGHJKMNPQRSTVWXYZ0123456789"  # 紛らわしいI/L/O/U を除外
    codes: list[str] = []
    for _ in range(count):
        raw = "".join(secrets_module.choice(alphabet) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def build_backup_code_entries(codes: list[str]) -> list[dict]:
    """平文コード一覧から保存用エントリ（ハッシュ＋未使用フラグ）を作る。"""
    return [{"hash": hash_backup_code(c), "used": False} for c in codes]


def count_unused_backup_codes(entries: list[dict] | None) -> int:
    """未使用のバックアップコード数を返す。"""
    if not entries:
        return 0
    return sum(1 for e in entries if not e.get("used"))


def match_backup_code(entries: list[dict] | None, code: str) -> int | None:
    """コードに一致する未使用エントリのインデックスを返す（定数時間比較）。無ければNone。"""
    if not entries:
        return None
    target = hash_backup_code(code)
    for i, entry in enumerate(entries):
        if entry.get("used"):
            continue
        if hmac.compare_digest(str(entry.get("hash", "")), target):
            return i
    return None


async def regenerate_backup_codes(
    db: AsyncSession, user_id: UUID, current_code: str, timestamp: int
) -> list[str] | None:
    """現在のTOTPコードを検証し、バックアップコードを再生成して保存する。

    平文コードを返す（呼び出し側で一度だけ表示）。MFA未有効・コード不正なら None。
    既存のバックアップコードは全て無効化される（再生成）。
    """
    user = await _get_user(db, user_id)
    if user is None or not user.mfa_enabled or not user.mfa_secret:
        return None
    if not await verify_and_consume_totp(db, user, current_code, timestamp):
        return None
    codes = generate_backup_codes()
    user.mfa_backup_codes = build_backup_code_entries(codes)
    await db.flush()
    return codes


async def consume_backup_code(db: AsyncSession, user, code: str) -> bool:
    """ログイン時のバックアップコード検証＋消費（単回使用）。一致すれば used=True にする。"""
    entries = user.mfa_backup_codes
    idx = match_backup_code(entries, code)
    if idx is None:
        return False
    # JSONBの部分更新はSQLAlchemyの変更検知に載らないため、リストを作り直して再代入する。
    updated = [dict(e) for e in entries]
    updated[idx]["used"] = True
    user.mfa_backup_codes = updated
    await db.flush()
    return True
