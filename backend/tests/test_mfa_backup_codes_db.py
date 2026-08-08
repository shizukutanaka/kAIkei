import pytest
from sqlalchemy import select

from app.models.models import User
from app.services import mfa

pytestmark = pytest.mark.db

TS = 1234567890


async def _enable_mfa(db, user_id, ts=TS):
    secret, _ = await mfa.setup_mfa(db, user_id)
    assert await mfa.enable_mfa(db, user_id, mfa.totp_code(secret, ts), ts) is True
    return secret


async def _get_user(db, user_id):
    return (await db.execute(select(User).where(User.user_id == user_id))).scalar_one()


async def test_regenerate_requires_valid_totp(db_session, seed_company):
    uid = seed_company["user_id"]
    secret = await _enable_mfa(db_session, uid)

    # 不正なコードでは再生成できない
    assert await mfa.regenerate_backup_codes(db_session, uid, "000000", TS + 60) is None

    codes = await mfa.regenerate_backup_codes(db_session, uid, mfa.totp_code(secret, TS + 60), TS + 60)
    assert codes is not None and len(codes) == 10

    user = await _get_user(db_session, uid)
    assert mfa.count_unused_backup_codes(user.mfa_backup_codes) == 10
    # 平文はDBに保存されない
    assert all(c not in str(user.mfa_backup_codes) for c in codes)


async def test_backup_code_is_single_use(db_session, seed_company):
    uid = seed_company["user_id"]
    secret = await _enable_mfa(db_session, uid)
    codes = await mfa.regenerate_backup_codes(db_session, uid, mfa.totp_code(secret, TS + 60), TS + 60)
    user = await _get_user(db_session, uid)

    # 1回目は成功、同じコードの2回目は失敗（単回使用）
    assert await mfa.consume_backup_code(db_session, user, codes[0]) is True
    assert await mfa.consume_backup_code(db_session, user, codes[0]) is False
    assert mfa.count_unused_backup_codes(user.mfa_backup_codes) == 9

    # 別のコードはまだ使える
    assert await mfa.consume_backup_code(db_session, user, codes[1]) is True
    assert mfa.count_unused_backup_codes(user.mfa_backup_codes) == 8


async def test_unknown_backup_code_rejected(db_session, seed_company):
    uid = seed_company["user_id"]
    secret = await _enable_mfa(db_session, uid)
    await mfa.regenerate_backup_codes(db_session, uid, mfa.totp_code(secret, TS + 60), TS + 60)
    user = await _get_user(db_session, uid)
    assert await mfa.consume_backup_code(db_session, user, "ZZZZZ-99999") is False


async def test_regenerate_invalidates_previous_codes(db_session, seed_company):
    uid = seed_company["user_id"]
    secret = await _enable_mfa(db_session, uid)
    old = await mfa.regenerate_backup_codes(db_session, uid, mfa.totp_code(secret, TS + 60), TS + 60)
    new = await mfa.regenerate_backup_codes(db_session, uid, mfa.totp_code(secret, TS + 120), TS + 120)
    assert set(old) & set(new) == set()

    user = await _get_user(db_session, uid)
    assert await mfa.consume_backup_code(db_session, user, old[0]) is False  # 旧コードは無効
    assert await mfa.consume_backup_code(db_session, user, new[0]) is True


async def test_backup_codes_cleared_on_disable_and_rotation(db_session, seed_company):
    uid = seed_company["user_id"]
    secret = await _enable_mfa(db_session, uid)
    await mfa.regenerate_backup_codes(db_session, uid, mfa.totp_code(secret, TS + 60), TS + 60)

    # 秘密鍵ローテーション（再setup）で旧バックアップコードは失効する
    await mfa.setup_mfa(db_session, uid, current_code=mfa.totp_code(secret, TS + 120), timestamp=TS + 120)
    user = await _get_user(db_session, uid)
    assert mfa.count_unused_backup_codes(user.mfa_backup_codes) == 0

    # MFA無効化でもクリアされる
    secret2 = user.mfa_secret
    assert await mfa.enable_mfa(db_session, uid, mfa.totp_code(secret2, TS + 180), TS + 180) is True
    await mfa.regenerate_backup_codes(db_session, uid, mfa.totp_code(secret2, TS + 240), TS + 240)
    assert await mfa.disable_mfa(db_session, uid, mfa.totp_code(secret2, TS + 300), TS + 300) is True
    user = await _get_user(db_session, uid)
    assert mfa.count_unused_backup_codes(user.mfa_backup_codes) == 0


async def test_regenerate_requires_mfa_enabled(db_session, seed_company):
    uid = seed_company["user_id"]
    # setupのみ（未有効化）では再生成できない
    secret, _ = await mfa.setup_mfa(db_session, uid)
    assert await mfa.regenerate_backup_codes(db_session, uid, mfa.totp_code(secret, TS), TS) is None
