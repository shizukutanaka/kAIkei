"""リフレッシュトークンのローテーションと再利用検知。

RFC 9700 (OAuth 2.0 Security Best Current Practice) §4.14.2 は、送信者拘束
（mTLS/DPoP）を使わない公開クライアントに対し、リフレッシュトークンの
ローテーションと再利用検知を求めている。

このアプリはトークンをブラウザの localStorage に置くため、XSS で盗まれ得る。
これまではサーバ側に発行記録が無く、

- 盗まれたトークンは有効期限（7日）まで使い放題
- 更新のたびに新しい7日が発行されるので実質無期限
- 正規利用者が使い続けても異常として検知できない
- 利用者を無効化・削除しても更新は通り続ける

という状態だった。

ここでは1回のログインを family とし、更新のたびに同じ family に新しい行を積む。
使用済みトークンが再度提示されたら、正規利用者と攻撃者の双方が同じトークンを
持っていたことになるので family ごと失効させる（＝再ログインを強制する）。

盗んだ側が先に使えば正規利用者の更新が弾かれ、正規利用者が先に使えば盗んだ側が
弾かれる。どちらの順序でも、盗難は「セッションが切れる」という形で表面化する。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import RefreshToken

# 同時更新（別タブ等）を盗難と誤判定しないための猶予。
#
# ブラウザのタブは localStorage を共有するため、2つのタブがほぼ同時に更新すると
# 片方は必ず「使用済み」を提示する。これを盗難として扱うと正常利用でセッションが
# 切れ、防御が実害を生む。一方で猶予を長く取ると盗難の検知が遅れる。
#
# 主要な実装（Auth0 等）と同じく往復の遅延を吸収できる数秒に留める。猶予内でも
# 「両者が同じ後継を受け取る」だけで、次の更新では必ずどちらかが弾かれるため、
# 検知は失われず遅れるだけ。
REUSE_GRACE_PERIOD = timedelta(seconds=3)


class RefreshTokenError(Exception):
    """リフレッシュトークンを受け付けられない理由。

    `reuse_detected` は「盗難の疑いがあり family を失効させた」ことを表す。
    呼び出し側で監視や通知に繋げられるよう、他の失敗と区別する。
    """

    def __init__(self, reason: str, *, reuse_detected: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.reuse_detected = reuse_detected


def _expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)


async def issue_new_family(db: AsyncSession, user_id: uuid.UUID) -> RefreshToken:
    """ログイン時に新しい family を開始する。"""
    token = RefreshToken(
        token_id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        user_id=user_id,
        expires_at=_expiry(),
    )
    db.add(token)
    await db.flush()
    return token


async def revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    """family 内の未失効トークンをすべて失効させる。"""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def _as_utc(value: datetime) -> datetime:
    """naive な datetime を UTC とみなして比較可能にする。

    列は timezone 付きだが、DBやドライバによっては naive で返ることがあるため。
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _successor_within_grace(db: AsyncSession, row: RefreshToken) -> RefreshToken | None:
    """同時更新とみなせる範囲なら、先に発行済みの後継を返す。

    ブラウザのタブは localStorage を共有するため、2つのタブがほぼ同時に更新すると
    片方は「使用済み」のトークンを提示することになる。これを盗難として扱うと、
    正常な利用でセッションが切れてしまい、防御が実害を生む。

    猶予は数秒に留め、後継がまだ未使用・未失効の場合だけ許す。時間を置いてから
    現れた再提示（＝盗まれたトークンの利用）は従来どおり検知される。
    """
    if row.replaced_by_id is None:
        return None
    if datetime.now(UTC) - _as_utc(row.used_at) > REUSE_GRACE_PERIOD:
        return None

    successor = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_id == row.replaced_by_id))
    ).scalar_one_or_none()
    if successor is None or successor.revoked_at is not None or successor.used_at is not None:
        return None
    return successor


async def rotate(db: AsyncSession, token_id: uuid.UUID) -> RefreshToken:
    """提示されたトークンを使用済みにし、同じ family の新しいトークンを返す。

    受け付けられない場合は `RefreshTokenError` を送出する。
    """
    row = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_id == token_id))
    ).scalar_one_or_none()

    if row is None:
        # 台帳に無い＝失効済みで消されたか、そもそも発行していないトークン。
        raise RefreshTokenError("unknown refresh token")

    if row.revoked_at is not None:
        raise RefreshTokenError("refresh token has been revoked")

    if row.used_at is not None:
        successor = await _successor_within_grace(db, row)
        if successor is not None:
            # 同時に更新しただけ（別タブ等）。同じ後継を返して取り違えを避ける。
            return successor
        # 使用済みのトークンが再度出てきた。正規利用者と攻撃者の双方が同じ
        # トークンを持っていたことになるので、family ごと失効させる。
        await revoke_family(db, row.family_id)
        raise RefreshTokenError("refresh token reuse detected", reuse_detected=True)

    if _as_utc(row.expires_at) <= datetime.now(UTC):
        raise RefreshTokenError("refresh token has expired")

    successor = RefreshToken(
        token_id=uuid.uuid4(),
        family_id=row.family_id,
        user_id=row.user_id,
        expires_at=_expiry(),
    )
    db.add(successor)
    row.used_at = datetime.now(UTC)
    row.replaced_by_id = successor.token_id
    await db.flush()
    return successor

