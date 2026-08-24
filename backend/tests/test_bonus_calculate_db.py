"""賞与計算（画面から実際に使われる経路）の検証。

`POST /bonus/calculate` は社会保険料を「賞与額の15%」で計算していた。
標準賞与額は1,000円未満切捨で、健康保険は年度累計573万円・厚生年金は1回
150万円が上限（健保法40条2項・厚年法24条の4）。率を直接掛けると切り捨ても
上限も効かず、高額賞与で過大に徴収する。
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.models import BonusRecord, Company, Employee, Tenant, User
from app.services.social_insurance import (
    DEFAULT_CARE_INSURANCE_RATE,
    DEFAULT_HEALTH_INSURANCE_RATE,
    PENSION_STANDARD_BONUS_PER_PAYMENT_CAP,
    SocialInsurancePremiumService,
    standard_bonus_amounts,
)

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

YEAR = 2026
BASE_SALARY = Decimal("400000")


@pytest_asyncio.fixture
async def api(api_client):
    return api_client


@pytest_asyncio.fixture
async def company(db_session):
    from app.core.security import create_access_token

    tenant = Tenant(tenant_name="BN", tenant_code=f"BN-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    co = Company(
        tenant_id=tenant.tenant_id,
        company_name="賞与テスト",
        company_code=f"BN-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(co)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"bn-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="Admin",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return {"company_id": co.company_id, "token": create_access_token(str(user.user_id))}


async def _add_employee(db_session, company_id, birth_date: date | None = None, dependents: int = 0) -> Employee:
    emp = Employee(
        company_id=company_id,
        employee_code=f"E-{uuid.uuid4().hex[:6]}",
        employee_name="賞与 太郎",
        base_salary=BASE_SALARY,
        hourly_rate=Decimal("2500"),
        hire_date=date(2020, 4, 1),
        birth_date=birth_date,
        dependents=dependents,
        is_active=True,
    )
    db_session.add(emp)
    await db_session.flush()
    return emp


async def _calculate(api, company, months: str = "2.0"):
    return await api.post(
        "/api/v1/bonus/calculate",
        json={
            "company_id": str(company["company_id"]),
            "bonus_year": YEAR,
            "bonus_term": "summer",
            "bonus_base_months": months,
        },
        headers={"Authorization": f"Bearer {company['token']}"},
    )


def _expected_employee_premium(bonus: Decimal, *, paid_before: Decimal = Decimal("0"), care: bool = False):
    standard = standard_bonus_amounts(bonus, paid_before)
    return SocialInsurancePremiumService.compute_bonus(
        health_standard_bonus=standard.health,
        pension_standard_bonus=standard.pension,
        health_rate=DEFAULT_HEALTH_INSURANCE_RATE,
        care_rate=DEFAULT_CARE_INSURANCE_RATE,
        care_applicable=care,
    ).total_employee


async def test_bonus_is_calculated(api, company, db_session):
    await _add_employee(db_session, company["company_id"])

    res = await _calculate(api, company)

    assert res.status_code == 200, res.text
    record = res.json()[0]
    assert Decimal(record["bonus_amount"]) == BASE_SALARY * 2


async def test_social_insurance_uses_the_standard_bonus(api, company, db_session):
    """賞与額×率ではなく、標準賞与額から算出すること。"""
    await _add_employee(db_session, company["company_id"])

    record = (await _calculate(api, company)).json()[0]
    bonus = Decimal(record["bonus_amount"])

    assert Decimal(record["social_insurance"]) == _expected_employee_premium(bonus)
    # 旧実装（賞与額の15%）とは一致しないこと。
    assert Decimal(record["social_insurance"]) != (bonus * Decimal("0.15")).quantize(Decimal("1"))


async def test_pension_cap_limits_a_large_bonus(api, company, db_session):
    """厚生年金の標準賞与額は1回150万円まで。上限が効くこと。"""
    await _add_employee(db_session, company["company_id"])

    # 月給40万 × 5ヶ月 = 200万円（厚生年金の上限150万円を超える）
    record = (await _calculate(api, company, months="5.0")).json()[0]
    bonus = Decimal(record["bonus_amount"])
    assert bonus > PENSION_STANDARD_BONUS_PER_PAYMENT_CAP

    assert Decimal(record["social_insurance"]) == _expected_employee_premium(bonus)
    # 上限を無視していれば、率を直接掛けた額に近づく。
    assert Decimal(record["social_insurance"]) < (bonus * Decimal("0.15")).quantize(Decimal("1"))


async def test_care_insurance_applies_from_age_40(api, company, db_session):
    """40歳以上65歳未満は介護保険料を上乗せすること。"""
    await _add_employee(db_session, company["company_id"], birth_date=date(1980, 1, 1))

    record = (await _calculate(api, company)).json()[0]
    bonus = Decimal(record["bonus_amount"])

    assert Decimal(record["social_insurance"]) == _expected_employee_premium(bonus, care=True)
    assert Decimal(record["social_insurance"]) > _expected_employee_premium(bonus, care=False)


async def test_health_cap_counts_bonuses_already_paid_this_year(api, company, db_session):
    """健康保険の年度累計573万円の上限に、支給済みの賞与が算入されること。"""
    emp = await _add_employee(db_session, company["company_id"])
    already = Decimal("5000000")
    db_session.add(
        BonusRecord(
            employee_id=emp.employee_id,
            company_id=company["company_id"],
            bonus_year=YEAR,
            bonus_term="winter",
            bonus_amount=already,
            bonus_base_months=Decimal("0"),
            performance_factor=Decimal("1.00"),
            income_tax=Decimal("0"),
            social_insurance=Decimal("0"),
            total_deductions=Decimal("0"),
            net_pay=already,
            status="calculated",
        )
    )
    await db_session.flush()

    record = (await _calculate(api, company)).json()[0]
    bonus = Decimal(record["bonus_amount"])

    assert Decimal(record["social_insurance"]) == _expected_employee_premium(bonus, paid_before=already)
    # 累計を無視した場合より少ないこと（健康保険の残枠で頭打ちになる）。
    assert Decimal(record["social_insurance"]) < _expected_employee_premium(bonus)


async def test_income_tax_is_disclosed_as_an_estimate(api, company, db_session):
    """賞与の源泉所得税は算出率表が未対応なので概算だと伝えること。"""
    await _add_employee(db_session, company["company_id"])

    record = (await _calculate(api, company)).json()[0]

    assert record["estimated_fields"] == ["income_tax"]
    assert "概算" in (record["estimate_notice"] or "")


async def test_income_tax_is_not_a_flat_rate(api, company, db_session):
    """賞与の源泉所得税が一律10.21%ではなくなっていること。"""
    from app.services.monthly_withholding import estimate_bonus_withholding
    from app.services.standard_remuneration import StandardRemunerationService

    emp = await _add_employee(db_session, company["company_id"])
    record = (await _calculate(api, company)).json()[0]

    bonus = Decimal(record["bonus_amount"])
    grade = StandardRemunerationService.lookup_health_grade(BASE_SALARY)
    monthly_social = SocialInsurancePremiumService.compute(
        standard_monthly_remuneration=grade.standard_monthly_remuneration,
        health_rate=DEFAULT_HEALTH_INSURANCE_RATE,
        care_rate=DEFAULT_CARE_INSURANCE_RATE,
        care_applicable=False,
    ).total_employee
    expected = estimate_bonus_withholding(
        monthly_gross=BASE_SALARY,
        monthly_social_insurance=monthly_social,
        bonus_gross=bonus,
        bonus_social_insurance=Decimal(record["social_insurance"]),
        dependents=emp.dependents,
    )

    assert Decimal(record["income_tax"]) == expected
    assert Decimal(record["income_tax"]) != (bonus * Decimal("0.1021")).quantize(Decimal("1"))


async def test_dependents_reduce_the_bonus_withholding(api, company, db_session):
    """扶養親族等の数が賞与の源泉所得税にも効くこと。"""
    none = await _add_employee(db_session, company["company_id"])
    without = Decimal((await _calculate(api, company)).json()[0]["income_tax"])

    await _add_employee(db_session, company["company_id"], dependents=4)
    records = (await _calculate(api, company)).json()
    with_deps = min(Decimal(r["income_tax"]) for r in records)

    assert with_deps < without, "扶養親族等の数が効いていない"
    assert none is not None
