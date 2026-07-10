import pytest

from app.services import security_policy

pytestmark = pytest.mark.db


async def test_upsert_creates_then_updates(db_session, seed_company):
    tid = seed_company["tenant_id"]
    p = await security_policy.upsert_policy(db_session, tid, require_mfa=True, allowed_ip_cidrs=["192.168.1.5/24"])
    assert p.require_mfa is True
    # host bits normalized away by normalize_cidrs
    assert p.allowed_ip_cidrs == ["192.168.1.0/24"]

    p2 = await security_policy.upsert_policy(db_session, tid, require_mfa=False)
    assert p2.require_mfa is False
    assert p2.allowed_ip_cidrs == ["192.168.1.0/24"]  # unchanged
    assert p2.tenant_security_policy_id == p.tenant_security_policy_id


async def test_check_ip_access(db_session, seed_company):
    tid = seed_company["tenant_id"]
    await security_policy.upsert_policy(db_session, tid, allowed_ip_cidrs=["10.0.0.0/8"])
    assert await security_policy.check_ip_access(db_session, tid, "10.5.5.5") is True
    assert await security_policy.check_ip_access(db_session, tid, "192.168.0.1") is False


async def test_no_policy_allows_all(db_session, seed_company):
    # different tenant with no policy row -> unrestricted
    tid = seed_company["tenant_id"]
    assert await security_policy.check_ip_access(db_session, tid, "203.0.113.9") is True
