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

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from app.api.v1.endpoints.payroll import ESTIMATED_PAYROLL_FIELDS
from app.core.database import get_db
from app.main import app
from app.models.models import Company, Employee, Tenant, User
from app.services.overtime_pay import OVERTIME_MONTHLY_THRESHOLD_HOURS

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

HOURLY = Decimal("2000")


@pytest_asyncio.fixture
async def api(db_session, monkeypatch):
    import contextlib

    from app.middleware import audit_log, idempotency, ip_restriction

    @contextlib.asynccontextmanager
    async def _test_session():
        yield db_session

    for module in (audit_log, idempotency, ip_restriction):
        monkeypatch.setattr(module, "async_session_factory", _test_session)

    app.dependency_overrides[get_db] = lambda: db_session
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


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


async def _add_employee(db_session, company_id) -> Employee:
    emp = Employee(
        company_id=company_id,
        employee_code=f"E-{uuid.uuid4().hex[:6]}",
        employee_name="残業 太郎",
        base_salary=Decimal("300000"),
        hourly_rate=HOURLY,
        hire_date=date(2024, 4, 1),
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
