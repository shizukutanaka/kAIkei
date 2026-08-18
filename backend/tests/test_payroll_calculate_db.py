"""月次給与計算（画面から実際に使われる経路）の検証。

このリポジトリには源泉徴収・社会保険・割増賃金の実装が個別に存在するが、
**画面から呼ばれる `/payroll/calculate` はそれらを使っていなかった**。
割増賃金は一律1.25倍で、月60時間超に1.5倍を適用する労基法37条に反しており、
残業の多い従業員が過少払いになる。

ここでは実際にエンドポイントを叩いて、支給額が法定の割増率で計算されること、
および法定の算出方法が未実装の項目が「概算」として利用者に伝わることを固定する。
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.api.v1.endpoints.payroll import ESTIMATED_PAYROLL_FIELDS
from app.models.models import Company, Employee, Tenant, User
from app.services.overtime_pay import OVERTIME_MONTHLY_THRESHOLD_HOURS
from app.services.social_insurance import (
    DEFAULT_CARE_INSURANCE_RATE,
    DEFAULT_HEALTH_INSURANCE_RATE,
    SocialInsurancePremiumService,
)
from app.services.standard_remuneration import StandardRemunerationService

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

HOURLY = Decimal("2000")


@pytest_asyncio.fixture
async def api(api_client):
    """共有の `api_client`（conftest.py）を使う。

    ミドルウェアのセッション差し替えとレート制限の解除はそこに集約している。
    """
    return api_client


@pytest_asyncio.fixture
async def company(db_session):
    from app.core.security import create_access_token

    tenant = Tenant(tenant_name="PR", tenant_code=f"PR-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    co = Company(
        tenant_id=tenant.tenant_id,
        company_name="給与テスト",
        company_code=f"PR-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(co)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"pr-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="Admin",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return {
        "company_id": co.company_id,
        "token": create_access_token(str(user.user_id)),
    }


async def _add_employee(db_session, company_id, birth_date: date | None = None) -> Employee:
    emp = Employee(
        company_id=company_id,
        employee_code=f"E-{uuid.uuid4().hex[:6]}",
        employee_name="残業 太郎",
        base_salary=Decimal("300000"),
        hourly_rate=HOURLY,
        hire_date=date(2024, 4, 1),
        birth_date=birth_date,
        is_active=True,
    )
    db_session.add(emp)
    await db_session.flush()
    return emp


async def _calculate(api, company, emp, hours: str):
    return await api.post(
        "/api/v1/payroll/calculate",
        json={
            "company_id": str(company["company_id"]),
            "payroll_year": 2026,
            "payroll_month": 4,
            "overtime_hours": {str(emp.employee_id): hours},
        },
        headers={"Authorization": f"Bearer {company['token']}"},
    )


async def test_overtime_within_60_hours_uses_the_125_rate(api, company, db_session):
    emp = await _add_employee(db_session, company["company_id"])

    res = await _calculate(api, company, emp, "10")

    assert res.status_code == 200, res.text
    record = res.json()[0]
    assert Decimal(record["overtime_pay"]) == HOURLY * 10 * Decimal("1.25")


async def test_overtime_over_60_hours_uses_the_150_rate(api, company, db_session):
    """月60時間超の割増は1.5倍（労基法37条）。

    一律1.25倍だと超過分が不足し、賃金の未払いになる。
    """
    emp = await _add_employee(db_session, company["company_id"])

    res = await _calculate(api, company, emp, "80")

    assert res.status_code == 200, res.text
    record = res.json()[0]

    threshold = OVERTIME_MONTHLY_THRESHOLD_HOURS
    expected = HOURLY * threshold * Decimal("1.25") + HOURLY * (Decimal("80") - threshold) * Decimal("1.50")
    assert Decimal(record["overtime_pay"]) == expected

    flat_rate = HOURLY * Decimal("80") * Decimal("1.25")
    assert Decimal(record["overtime_pay"]) > flat_rate, "一律1.25倍のままで、超過分が不足している"


async def test_gross_and_net_follow_the_corrected_overtime(api, company, db_session):
    """割増賃金の修正が総支給・差引支給まで反映されること。"""
    emp = await _add_employee(db_session, company["company_id"])

    res = await _calculate(api, company, emp, "80")
    record = res.json()[0]

    gross = Decimal(record["base_salary"]) + Decimal(record["overtime_pay"])
    assert Decimal(record["total_gross"]) == gross
    assert Decimal(record["net_pay"]) == gross - Decimal(record["total_deductions"])


async def test_estimated_fields_are_disclosed(api, company, db_session):
    """法定の算出方法が未実装の項目は「概算」と分かるようにすること。

    源泉所得税は税額表、社会保険料は標準報酬月額の等級と都道府県別料率が必要だが
    いずれも未対応。概算だと分からないまま給与明細や納付額に使われると実害が出る。
    """
    emp = await _add_employee(db_session, company["company_id"])

    res = await _calculate(api, company, emp, "10")
    record = res.json()[0]

    assert set(record["estimated_fields"]) == set(ESTIMATED_PAYROLL_FIELDS)
    assert record["estimate_notice"], "概算である旨が利用者に伝わらない"
    assert "概算" in record["estimate_notice"]


async def test_zero_overtime_is_handled(api, company, db_session):
    emp = await _add_employee(db_session, company["company_id"])

    res = await _calculate(api, company, emp, "0")

    assert res.status_code == 200
    assert Decimal(res.json()[0]["overtime_pay"]) == 0


def _expected_social_insurance(gross: Decimal, *, care: bool) -> Decimal:
    """検証済みサービスから期待値を組み立てる（実装の写経にしない）。"""
    grade = StandardRemunerationService.lookup_health_grade(gross)
    return SocialInsurancePremiumService.compute(
        standard_monthly_remuneration=grade.standard_monthly_remuneration,
        health_rate=DEFAULT_HEALTH_INSURANCE_RATE,
        care_rate=DEFAULT_CARE_INSURANCE_RATE,
        care_applicable=care,
    ).total_employee


async def test_social_insurance_uses_the_standard_remuneration_grade(api, company, db_session):
    """社会保険料が総額×率ではなく、標準報酬月額の等級で決まること。

    等級は幅を持つため、総支給が変わっても同じ等級なら保険料は変わらない。
    総額に率を掛ける実装だと、ここで金額が動いてしまう。
    """
    emp = await _add_employee(db_session, company["company_id"])

    res = await _calculate(api, company, emp, "10")
    record = res.json()[0]

    gross = Decimal(record["total_gross"])
    assert Decimal(record["social_insurance"]) == _expected_social_insurance(gross, care=False)

    # 総額の15%（旧実装）とは一致しないこと。
    assert Decimal(record["social_insurance"]) != (gross * Decimal("0.15")).quantize(Decimal("1"))


async def test_care_insurance_is_collected_from_age_40(api, company, db_session):
    """40歳以上65歳未満は介護保険料を上乗せすること。"""
    young = await _add_employee(db_session, company["company_id"], birth_date=date(2000, 1, 1))
    res = await _calculate(api, company, young, "10")
    without_care = Decimal(res.json()[0]["social_insurance"])

    middle = await _add_employee(db_session, company["company_id"], birth_date=date(1980, 1, 1))
    res = await _calculate(api, company, middle, "10")
    records = {r["employee_id"]: r for r in res.json()}
    with_care = Decimal(records[str(middle.employee_id)]["social_insurance"])

    assert with_care > without_care, "介護保険料が上乗せされていない"
    gross = Decimal(records[str(middle.employee_id)]["total_gross"])
    assert with_care == _expected_social_insurance(gross, care=True)


async def test_company_rate_overrides_the_default(api, company, db_session):
    """健康保険料率は都道府県・年度で変わるため、会社の設定が効くこと。"""
    from app.models.models import Company

    emp = await _add_employee(db_session, company["company_id"])
    before = Decimal((await _calculate(api, company, emp, "0")).json()[0]["social_insurance"])

    co = (
        await db_session.execute(select(Company).where(Company.company_id == company["company_id"]))
    ).scalar_one()
    co.health_insurance_rate = DEFAULT_HEALTH_INSURANCE_RATE * 2
    await db_session.flush()

    after = Decimal((await _calculate(api, company, emp, "0")).json()[0]["social_insurance"])
    assert after > before, "会社ごとの料率設定が反映されていない"


async def test_only_income_tax_remains_an_estimate(api, company, db_session):
    """社会保険料は概算の一覧から外れ、源泉所得税だけが残ること。"""
    emp = await _add_employee(db_session, company["company_id"])

    record = (await _calculate(api, company, emp, "10")).json()[0]

    assert record["estimated_fields"] == ["income_tax"]
    assert "社会保険料" not in (record["estimate_notice"] or "")
