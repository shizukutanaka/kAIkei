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


def verify_totp(
    secret: str,
    code: str,
    timestamp: int,
    window: int = 1,
    period: int = DEFAULT_PERIOD_SECONDS,
    digits: int = DEFAULT_DIGITS,
) -> bool:
    """TOTPコードを検証する。時計ずれ許容として前後windowステップを受理する。"""
    cleaned = code.strip().replace(" ", "")
    if not cleaned.isdigit() or len(cleaned) != digits:
        return False
    try:
        key = _decode_secret(secret)
    except (ValueError, TypeError):
        return False
    counter = int(timestamp) // period
    for offset in range(-window, window + 1):
        if hmac.compare_digest(_hotp(key, counter + offset, digits), cleaned):
            return True
    return False


def build_otpauth_uri(secret: str, account_name: str, issuer: str = "kAIkei") -> str:
    """認証アプリ登録用の otpauth:// URI を組み立てる。"""
    label = f"{quote(issuer)}:{quote(account_name)}"
    return (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits={DEFAULT_DIGITS}"
        f"&period={DEFAULT_PERIOD_SECONDS}"
    )


async def setup_mfa(db: AsyncSession, user_id: UUID) -> tuple[str, str] | None:
    """新しい秘密鍵を発行して保存する（この時点では未有効）。

    Returns:
        (secret, otpauth_uri)。ユーザーが見つからなければ None。
    """
    from app.models.models import User

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    secret = generate_totp_secret()
    user.mfa_secret = secret
    user.mfa_enabled = False
    await db.flush()
    return secret, build_otpauth_uri(secret, user.email)


async def enable_mfa(db: AsyncSession, user_id: UUID, code: str, timestamp: int) -> bool:
    """setup済みの秘密鍵に対しコードを検証し、MFAを有効化する。"""
    from app.models.models import User

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.mfa_secret:
        return False
    if not verify_totp(user.mfa_secret, code, timestamp):
        return False
    user.mfa_enabled = True
    await db.flush()
    return True


async def disable_mfa(db: AsyncSession, user_id: UUID, code: str, timestamp: int) -> bool:
    """コードを検証してMFAを無効化し、秘密鍵を破棄する。"""
    from app.models.models import User

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.mfa_enabled or not user.mfa_secret:
        return False
    if not verify_totp(user.mfa_secret, code, timestamp):
        return False
    user.mfa_enabled = False
    user.mfa_secret = None
    await db.flush()
    return True
