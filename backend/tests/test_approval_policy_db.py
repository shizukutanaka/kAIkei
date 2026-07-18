from decimal import Decimal

import pytest

from app.services import approval_policy

pytestmark = pytest.mark.db


async def test_create_and_resolve_steps(db_session, seed_company):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]

    await approval_policy.create_policy(
        db_session, tenant_id=tid, company_id=cid,
        document_type="expense", approver_role="manager", step_order=1, min_amount=Decimal("0"),
    )
    await approval_policy.create_policy(
        db_session, tenant_id=tid, company_id=cid,
        document_type="expense", approver_role="director", step_order=2, min_amount=Decimal("100000"),
    )

    # small amount -> only step 1
    small = await approval_policy.resolve_required_steps(db_session, cid, "expense", Decimal("5000"))
    assert small == ["manager"]

    # large amount -> both steps in order
    large = await approval_policy.resolve_required_steps(db_session, cid, "expense", Decimal("200000"))
    assert large == ["manager", "director"]


async def test_delete_policy(db_session, seed_company):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    policy = await approval_policy.create_policy(
        db_session, tenant_id=tid, company_id=cid,
        document_type="invoice", approver_role="manager",
    )
    assert await approval_policy.delete_policy(db_session, cid, policy.approval_policy_id) is True
    assert await approval_policy.delete_policy(db_session, cid, policy.approval_policy_id) is False
    remaining = await approval_policy.list_policies(db_session, cid)
    assert remaining == []
