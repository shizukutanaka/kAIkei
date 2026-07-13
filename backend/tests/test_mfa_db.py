import uuid

import pytest

from app.services import mfa

pytestmark = pytest.mark.db

TS = 1234567890


async def test_setup_enable_disable_flow(db_session, seed_company):
    user_id = seed_company["user_id"]

    result = await mfa.setup_mfa(db_session, user_id)
    assert result is not None
    secret, uri = result
    assert uri.startswith("otpauth://totp/kAIkei:tester%40example.com?")

    # setupだけではログインMFAは要求されない（enabled=False）
    assert await mfa.enable_mfa(db_session, user_id, "000000", TS) is False

    code = mfa.totp_code(secret, TS)
    assert await mfa.enable_mfa(db_session, user_id, code, TS) is True

    # 無効化: 間違ったコードは拒否。有効化時とは別の時間ステップのコードを使う
    # （同一コードの使い回しはリプレイ防止ガードにより拒否されるため）。
    disable_ts = TS + 60
    disable_code = mfa.totp_code(secret, disable_ts)
    assert await mfa.disable_mfa(db_session, user_id, "000000", disable_ts) is False
    assert await mfa.disable_mfa(db_session, user_id, disable_code, disable_ts) is True
    assert await mfa.disable_mfa(db_session, user_id, disable_code, disable_ts) is False


async def test_setup_unknown_user_returns_none(db_session):
    assert await mfa.setup_mfa(db_session, uuid.uuid4()) is None


async def test_setup_rotation_while_enabled_requires_current_code(db_session, seed_company):
    """盗まれたアクセストークンだけでは、有効化済みMFAの秘密鍵を差し替えられない。"""
    from sqlalchemy import select

    from app.models.models import User

    user_id = seed_company["user_id"]

    secret, _ = await mfa.setup_mfa(db_session, user_id)
    code = mfa.totp_code(secret, TS)
    assert await mfa.enable_mfa(db_session, user_id, code, TS) is True

    # current_code なしで再setupを試みる → MfaReauthRequired（バイパス不可）
    with pytest.raises(mfa.MfaReauthRequired):
        await mfa.setup_mfa(db_session, user_id)

    # 間違ったcurrent_codeでも同様に拒否される
    with pytest.raises(mfa.MfaReauthRequired):
        await mfa.setup_mfa(db_session, user_id, current_code="000000", timestamp=TS + 30)

    # MFAは有効なまま、秘密鍵も差し替わっていない（setup_mfaの失敗は状態を変更しない）
    result = await db_session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one()
    assert user.mfa_enabled is True
    assert user.mfa_secret == secret


async def test_setup_rotation_with_valid_current_code_succeeds(db_session, seed_company):
    user_id = seed_company["user_id"]

    secret, _ = await mfa.setup_mfa(db_session, user_id)
    code = mfa.totp_code(secret, TS)
    assert await mfa.enable_mfa(db_session, user_id, code, TS) is True

    # ローテーション用に、初回enable時とは別の（未使用の）時間ステップのコードを使う
    rotate_ts = TS + 60
    rotate_code = mfa.totp_code(secret, rotate_ts)
    new_secret, _ = await mfa.setup_mfa(db_session, user_id, current_code=rotate_code, timestamp=rotate_ts)
    assert new_secret != secret
    # 有効化はやり直しが必要（rotate後は一旦 enabled=False に戻る）
    new_code = mfa.totp_code(new_secret, rotate_ts + 60)
    assert await mfa.enable_mfa(db_session, user_id, new_code, rotate_ts + 60) is True


async def test_login_code_cannot_be_replayed(db_session, seed_company):
    """同一のTOTPコードを2回連続で使い回すこと（リプレイ）はできない。"""
    from sqlalchemy import select

    from app.models.models import User

    user_id = seed_company["user_id"]
    secret, _ = await mfa.setup_mfa(db_session, user_id)
    enable_code = mfa.totp_code(secret, TS)
    assert await mfa.enable_mfa(db_session, user_id, enable_code, TS) is True

    result = await db_session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one()

    # ログイン用に、有効化時に消費済みの時間ステップとは別のコードを使う
    login_ts = TS + 60
    login_code = mfa.totp_code(secret, login_ts)

    # ログイン相当の検証: 1回目は成功
    assert await mfa.verify_and_consume_totp(db_session, user, login_code, login_ts) is True
    # 同じコードの2回目（再送）は拒否される
    assert await mfa.verify_and_consume_totp(db_session, user, login_code, login_ts + 1) is False
    # 次の時間ステップの新しいコードは受理される
    next_code = mfa.totp_code(secret, login_ts + 30)
    assert await mfa.verify_and_consume_totp(db_session, user, next_code, login_ts + 30) is True
