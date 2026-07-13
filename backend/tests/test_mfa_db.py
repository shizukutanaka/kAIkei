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

    # 無効化: 間違ったコードは拒否、正しいコードで秘密鍵ごと破棄
    assert await mfa.disable_mfa(db_session, user_id, "000000", TS) is False
    assert await mfa.disable_mfa(db_session, user_id, code, TS) is True
    assert await mfa.disable_mfa(db_session, user_id, code, TS) is False


async def test_setup_unknown_user_returns_none(db_session):
    assert await mfa.setup_mfa(db_session, uuid.uuid4()) is None
