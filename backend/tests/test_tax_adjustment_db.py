from decimal import Decimal

import pytest

from app.services import tax_adjustment

pytestmark = pytest.mark.db


async def test_compute_taxable_income_with_rules(db_session, seed_company):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    rule = await tax_adjustment.create_rule(
        db_session, tenant_id=tid, company_id=cid, name="交際費限度超過",
        adjustment_type="addition", calculation_method="excess_over_limit",
        limit_amount=Decimal("800000"),
    )
    await tax_adjustment.create_rule(
        db_session, tenant_id=tid, company_id=cid, name="固定加算",
        adjustment_type="addition", calculation_method="fixed", fixed_amount=Decimal("50000"),
    )
    result = await tax_adjustment.compute_company_taxable_income(
        db_session, cid, Decimal("1000000"), base_amounts={str(rule.tax_adjustment_rule_id): Decimal("1000000")},
    )
    # 200,000 (excess) + 50,000 (fixed) additions
    assert result["total_additions"] == Decimal("250000")
    assert result["taxable_income"] == Decimal("1250000")


async def test_delete_rule(db_session, seed_company):
    tid, cid = seed_company["tenant_id"], seed_company["company_id"]
    rule = await tax_adjustment.create_rule(
        db_session, tenant_id=tid, company_id=cid, name="x",
        adjustment_type="subtraction", calculation_method="fixed", fixed_amount=Decimal("1"),
    )
    assert await tax_adjustment.delete_rule(db_session, cid, rule.tax_adjustment_rule_id) is True
    assert await tax_adjustment.list_rules(db_session, cid) == []
