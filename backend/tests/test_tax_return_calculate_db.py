"""消費税申告（画面から実際に使われる経路）の検証。

`POST /tax-returns/calculate` は課税売上・課税仕入を**売上・費用の一律80%/20%**
で按分していた。コード上も `"Simplified: assume 80% of revenue is taxable"` と
placeholder であることが書かれており、実際の取引内容と無関係な数値が
申告書に載る状態だった。簡易課税のみなし仕入率も事業区分によらず90%固定。

申告書はそのまま提出されうるので、仕訳の税区分から集計されることを固定する。
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.models import (
    Account,
    Company,
    JournalHeader,
    JournalLine,
    TaxRule,
    Tenant,
    User,
)
from app.services.simplified_consumption_tax import SIMPLIFIED_CONSUMPTION_TAX_RATES

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

YEAR = 2026


@pytest_asyncio.fixture
async def api(api_client):
    return api_client


@pytest_asyncio.fixture
async def books(db_session):
    """課税・非課税・輸出免税の売上と、課税仕入を持つ会社を用意する。"""
    from app.core.security import create_access_token

    tenant = Tenant(tenant_name="CT", tenant_code=f"CT-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    co = Company(
        tenant_id=tenant.tenant_id,
        company_name="消費税テスト",
        company_code=f"CT-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(co)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"ct-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="Admin",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    sales_account = Account(
        company_id=co.company_id,
        account_code="4000",
        account_name="売上",
        account_type="revenue",
        debit_credit="credit",
    )
    expense_account = Account(
        company_id=co.company_id,
        account_code="5000",
        account_name="仕入",
        account_type="expense",
        debit_credit="debit",
    )
    db_session.add_all([sales_account, expense_account])
    await db_session.flush()

    rules = {}
    for code, name, rate, tax_type in (
        ("T10", "課税10%", Decimal("0.10"), "taxable"),
        ("T08", "課税8%(軽減)", Decimal("0.08"), "taxable"),
        ("EXP", "輸出免税", Decimal("0"), "export"),
        ("NON", "非課税", Decimal("0"), "non_taxable"),
    ):
        rule = TaxRule(
            company_id=co.company_id,
            tax_code=code,
            tax_name=name,
            tax_rate=rate,
            tax_type=tax_type,
        )
        db_session.add(rule)
        await db_session.flush()
        rules[code] = rule

    header = JournalHeader(
        company_id=co.company_id,
        journal_number=f"J-{uuid.uuid4().hex[:8]}",
        transaction_date=date(YEAR, 6, 30),
        summary="消費税テスト",
        approval_status="approved",
        created_by=user.user_id,
    )
    db_session.add(header)
    await db_session.flush()

    def _line(n, account, side, amount, rule_code):
        return JournalLine(
            journal_header_id=header.journal_header_id,
            line_number=n,
            debit_credit=side,
            account_id=account.account_id,
            tax_rule_id=rules[rule_code].tax_rule_id if rule_code else None,
            amount=amount,
        )

    db_session.add_all(
        [
            _line(1, sales_account, "credit", Decimal("1000000"), "T10"),
            _line(2, sales_account, "credit", Decimal("500000"), "T08"),
            _line(3, sales_account, "credit", Decimal("300000"), "EXP"),
            _line(4, sales_account, "credit", Decimal("200000"), "NON"),
            _line(5, expense_account, "debit", Decimal("400000"), "T10"),
            _line(6, expense_account, "debit", Decimal("100000"), "NON"),
        ]
    )
    await db_session.flush()

    return {
        "company_id": co.company_id,
        "token": create_access_token(str(user.user_id)),
        "header": header,
        "sales_account": sales_account,
        "rules": rules,
    }


async def _calculate(api, books, filing_type="general", business_category=4):
    return await api.post(
        "/api/v1/tax-returns/calculate",
        json={
            "company_id": str(books["company_id"]),
            "tax_year": YEAR,
            "filing_type": filing_type,
            "business_category": business_category,
        },
        headers={"Authorization": f"Bearer {books['token']}"},
    )


async def test_taxable_sales_come_from_the_tax_rules(api, books):
    """課税売上が税区分から集計されること（一律按分ではない）。"""
    res = await _calculate(api, books)

    assert res.status_code == 201, res.text
    body = res.json()
    # 課税は 100万(10%) + 50万(8%) = 150万
    assert Decimal(body["taxable_sales"]) == Decimal("1500000")
    # 旧実装は 売上合計200万 × 80% = 160万 だった。
    assert Decimal(body["taxable_sales"]) != Decimal("1600000")


async def test_export_and_non_taxable_are_separated(api, books):
    """輸出免税は非課税と別枠で集計されること。"""
    body = (await _calculate(api, books)).json()

    assert Decimal(body["export_taxable_sales"]) == Decimal("300000")
    assert Decimal(body["non_taxable_sales"]) == Decimal("200000")


async def test_output_tax_respects_each_rate(api, books):
    """軽減税率が混在しても率ごとに計算すること。

    100万×10% + 50万×8% = 14万。一律10%なら15万になってしまう。
    """
    body = (await _calculate(api, books)).json()

    assert Decimal(body["output_tax"]) == Decimal("140000")
    assert Decimal(body["output_tax"]) != Decimal("150000")


async def test_general_filing_uses_actual_purchases(api, books):
    """一般課税は実際の課税仕入から控除額を求めること。"""
    body = (await _calculate(api, books)).json()

    assert Decimal(body["purchases_subject_to_tax"]) == Decimal("400000")
    assert Decimal(body["input_tax"]) == Decimal("40000")
    assert Decimal(body["tax_payable"]) == Decimal("100000")


async def test_simplified_filing_uses_the_business_category(api, books):
    """簡易課税は事業区分ごとのみなし仕入率を使うこと（90%固定ではない）。"""
    body = (await _calculate(api, books, filing_type="simplified", business_category=5)).json()

    output = Decimal(body["output_tax"])
    expected = (output * SIMPLIFIED_CONSUMPTION_TAX_RATES[5]).to_integral_value(rounding="ROUND_DOWN")
    assert Decimal(body["input_tax"]) == expected

    # 事業区分を変えれば控除額も変わる。
    other = (await _calculate(api, books, filing_type="simplified", business_category=1)).json()
    assert Decimal(other["input_tax"]) != Decimal(body["input_tax"])


async def test_no_warning_when_every_line_is_classified(api, books):
    """全明細に税区分があれば概算の警告を出さないこと。"""
    body = (await _calculate(api, books)).json()

    assert body["estimate_notice"] is None
    assert body["estimated_fields"] == []


async def test_unclassified_lines_are_reported(api, books, db_session):
    """税区分の無い明細があれば件数と金額を伝えること。

    黙って課税・非課税のどちらかに倒すと申告額が静かに狂う。
    """
    db_session.add(
        JournalLine(
            journal_header_id=books["header"].journal_header_id,
            line_number=99,
            debit_credit="credit",
            account_id=books["sales_account"].account_id,
            tax_rule_id=None,
            amount=Decimal("777000"),
        )
    )
    await db_session.flush()

    body = (await _calculate(api, books)).json()

    assert body["estimate_notice"] is not None
    assert "1件" in body["estimate_notice"]
    assert "777,000" in body["estimate_notice"]
    # 未分類は課税にも非課税にも入っていない。
    assert Decimal(body["taxable_sales"]) == Decimal("1500000")
    assert Decimal(body["non_taxable_sales"]) == Decimal("200000")
