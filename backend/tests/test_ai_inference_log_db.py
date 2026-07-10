from decimal import Decimal

import pytest

from app.services import ai_inference_log

pytestmark = pytest.mark.db


async def test_log_apply_and_stats(db_session, seed_company):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    log = await ai_inference_log.log_inference(
        db_session, tenant_id=tid, company_id=cid, source_type="journal_suggest",
        suggestion={"account_code": "1110", "amount": 1000}, confidence=Decimal("0.9"),
    )
    assert log.applied is False

    applied = await ai_inference_log.mark_applied(
        db_session, cid, log.ai_inference_log_id, final={"account_code": "5210", "amount": 1000},
    )
    assert applied.applied is True
    assert applied.correction_diff == {"account_code": {"from": "1110", "to": "5210"}}

    stats = await ai_inference_log.get_stats(db_session, cid)
    assert stats["total"] == 1
    assert stats["applied"] == 1
    assert stats["corrected"] == 1
