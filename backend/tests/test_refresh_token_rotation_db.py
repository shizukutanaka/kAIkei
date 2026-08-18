"""リフレッシュトークンのローテーションと再利用検知（RFC 9700 §4.14.2）。

このアプリはトークンをブラウザの localStorage に置くため XSS で盗まれ得る。
サーバ側に発行記録が無かった頃は、盗まれたトークンが有効期限まで使い放題で、
更新のたびに期限が延びるため実質無期限だった。

ここでは「盗まれたあと何が起きるか」を実際の手順で確認する。
"""
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.passwords import hash_password
from app.models.models import RefreshToken, Tenant, User
from app.services import refresh_tokens

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

PASSWORD = "correct-horse-battery-staple"


@pytest_asyncio.fixture
async def api(api_client):
    """共有の `api_client`（conftest.py）を使う。

    ミドルウェアのセッション差し替えとレート制限の解除はそこに集約している。
    """
    return api_client


@pytest_asyncio.fixture
async def user(db_session):
    tenant = Tenant(tenant_name="RT", tenant_code=f"RT-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    u = User(
        tenant_id=tenant.tenant_id,
        email=f"rt-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password(PASSWORD),
        display_name="RT User",
        role="admin",
        is_active=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


async def _login(api, user) -> dict:
    res = await api.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return res.json()


async def _refresh(api, token: str) -> httpx.Response:
    return await api.post("/api/v1/auth/refresh", json={"refresh_token": token})


async def _age_out_grace(db_session, user):
    """使用済みトークンの used_at を猶予より過去にずらす。

    「同時更新」ではなく「時間を置いた再提示」＝盗難の状況を作るため。
    """
    rows = (
        await db_session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user.user_id, RefreshToken.used_at.isnot(None)
            )
        )
    ).scalars().all()
    for row in rows:
        row.used_at = datetime.now(UTC) - refresh_tokens.REUSE_GRACE_PERIOD - timedelta(seconds=1)
    await db_session.flush()


async def test_login_then_refresh_succeeds(api, user):
    tokens = await _login(api, user)
    res = await _refresh(api, tokens["refresh_token"])

    assert res.status_code == 200, res.text
    assert res.json()["refresh_token"] != tokens["refresh_token"], "毎回同じトークンが返っている"


async def test_old_token_stops_working_after_rotation(api, user, db_session):
    """更新したら古いトークンは使えなくなること（＝ローテーション）。

    同時更新の猶予を過ぎたあとで確認する。猶予内の再提示は別タブ等の
    正常な利用なので、そちらは test_simultaneous_refresh_does_not_look_like_theft
    が担当する。
    """
    tokens = await _login(api, user)
    first = tokens["refresh_token"]

    ok = await _refresh(api, first)
    assert ok.status_code == 200

    await _age_out_grace(db_session, user)

    again = await _refresh(api, first)
    assert again.status_code == 401, "使用済みのトークンがまだ通る"


async def test_reuse_revokes_the_whole_family(api, user, db_session):
    """盗まれたトークンが使われたら、正規利用者側も含めて失効すること。

    攻撃者がトークンを盗んで先に使い、正規利用者があとから（同時更新とは
    みなせない間隔を空けて）同じトークンを使う、という想定。再利用が検知され、
    その認証に紐づくセッションが全て切れる（＝再ログインを強制する）。
    """
    tokens = await _login(api, user)
    stolen = tokens["refresh_token"]

    # 攻撃者が先に使う。新しいトークンを手に入れる。
    attacker = await _refresh(api, stolen)
    assert attacker.status_code == 200
    attacker_token = attacker.json()["refresh_token"]

    await _age_out_grace(db_session, user)

    # 正規利用者が同じ（古い）トークンで更新 → 再利用として検知される。
    victim = await _refresh(api, stolen)
    assert victim.status_code == 401

    # 攻撃者が手に入れたトークンも道連れで失効していること。
    assert (await _refresh(api, attacker_token)).status_code == 401, (
        "再利用を検知したのに、攻撃者のトークンが生き残っている"
    )

    rows = (
        await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user.user_id))
    ).scalars().all()
    assert rows and all(r.revoked_at is not None for r in rows), "family が失効しきっていない"


async def test_simultaneous_refresh_does_not_look_like_theft(api, user):
    """別タブ等の同時更新でセッションを切らないこと。

    タブは localStorage を共有するため、2つがほぼ同時に更新すると片方は必ず
    「使用済み」を提示する。これを盗難として扱うと、正常な利用でログアウト
    させられ、防御がそのまま実害になる。猶予内なら同じ後継を返す。
    """
    tokens = await _login(api, user)
    first = tokens["refresh_token"]

    a = await _refresh(api, first)
    b = await _refresh(api, first)

    assert a.status_code == 200
    assert b.status_code == 200, "同時更新が盗難扱いされている"
    assert a.json()["refresh_token"] == b.json()["refresh_token"], (
        "同時更新なのに別々のトークンが出ており、片方が必ず失効する"
    )

    # 猶予で許した後も、後継トークンはそのまま使えること。
    assert (await _refresh(api, a.json()["refresh_token"])).status_code == 200


async def test_reuse_after_the_grace_period_is_still_detected(api, user, db_session):
    """猶予を過ぎた再提示は、これまで通り盗難として扱うこと。

    猶予の導入で検知そのものが失われていないことを固定する。
    """
    tokens = await _login(api, user)
    first = tokens["refresh_token"]

    assert (await _refresh(api, first)).status_code == 200
    await _age_out_grace(db_session, user)

    assert (await _refresh(api, first)).status_code == 401


async def test_deactivated_user_cannot_refresh(api, user, db_session):
    """利用者を無効化したら更新も止まること。

    以前はトークンだけを見ていたため、無効化しても有効期限いっぱい
    （最大7日）アクセスし続けられた。
    """
    tokens = await _login(api, user)

    user.is_active = False
    await db_session.flush()

    assert (await _refresh(api, tokens["refresh_token"])).status_code == 401


async def test_deleted_user_cannot_refresh(api, user, db_session):
    tokens = await _login(api, user)

    user.is_deleted = True
    await db_session.flush()

    assert (await _refresh(api, tokens["refresh_token"])).status_code == 401


async def test_token_without_jti_is_rejected(api, user):
    """台帳導入前に発行された古いトークンは受け付けないこと。

    失効させる手段が無いため、通してしまうと防御の穴になる。
    """
    from app.core.security import create_refresh_token

    legacy = create_refresh_token(subject=str(user.user_id))
    assert (await _refresh(api, legacy)).status_code == 401


async def test_access_token_is_not_accepted_as_refresh(api, user):
    tokens = await _login(api, user)
    assert (await _refresh(api, tokens["access_token"])).status_code == 401


async def test_expired_token_is_rejected(db_session, user):
    """期限切れは（再利用ではなく）期限切れとして弾くこと。"""
    issued = await refresh_tokens.issue_new_family(db_session, user.user_id)
    issued.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()

    with pytest.raises(refresh_tokens.RefreshTokenError) as exc:
        await refresh_tokens.rotate(db_session, issued.token_id)
    assert not exc.value.reuse_detected


async def test_unknown_token_is_rejected(db_session):
    with pytest.raises(refresh_tokens.RefreshTokenError):
        await refresh_tokens.rotate(db_session, uuid.uuid4())
