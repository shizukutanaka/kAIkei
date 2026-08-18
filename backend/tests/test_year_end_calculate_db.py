"""年末調整（画面から実際に使われる経路）の検証。

`POST /year-end/calculate` は所得控除を一切引かず、**給与収入そのものに税率を
掛けて**いた。給与所得控除・社会保険料控除・基礎控除を無視し、復興特別所得税も
加算していなかったため、年税額が実際の数倍になる。

年末調整の結果はそのまま還付・追徴の金額になるので、還付されるべき人に
多額の追徴が出ることを意味する。検証済みの YearEndAdjustmentService に
委ねたうえで、その金額を固定する。
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.models import Company, Employee, PayrollRecord, Tenant, User
from app.services.income_deduction import basic_deduction, dependent_deduction
from app.services.salary_deduction import SalaryIncomeDeductionService
from app.services.year_end_adjustment import YearEndAdjustmentService

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

YEAR = 2026
MONTHLY_GROSS = Decimal("400000")
MONTHLY_SOCIAL = Decimal("60000")
MONTHLY_TAX = Decimal("8000")


@pytest_asyncio.fixture
async def api(api_client):
    """共有の `api_client`（conftest.py）を使う。

    ミドルウェアのセッション差し替えとレート制限の解除はそこに集約している。
    """
    return api_client


@pytest_asyncio.fixture
async def setup(db_session):
    """12ヶ月分の給与実績を持つ従業員を1名用意する。"""
    from app.core.security import create_access_token

    tenant = Tenant(tenant_name="YE", tenant_code=f"YE-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.flush()
    co = Company(
        tenant_id=tenant.tenant_id,
        company_name="年調テスト",
        company_code=f"YE-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(co)
    await db_session.flush()
    user = User(
        tenant_id=tenant.tenant_id,
        email=f"ye-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x",
        display_name="Admin",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    emp = Employee(
        company_id=co.company_id,
        employee_code=f"E-{uuid.uuid4().hex[:6]}",
        employee_name="年調 花子",
        base_salary=MONTHLY_GROSS,
        hourly_rate=Decimal("2500"),
        hire_date=date(2020, 4, 1),
        is_active=True,
    )
    db_session.add(emp)
    await db_session.flush()

    for month in range(1, 13):
        db_session.add(
            PayrollRecord(
                employee_id=emp.employee_id,
                company_id=co.company_id,
                payroll_year=YEAR,
                payroll_month=month,
                base_salary=MONTHLY_GROSS,
                overtime_hours=Decimal("0"),
                overtime_pay=Decimal("0"),
                total_gross=MONTHLY_GROSS,
                income_tax=MONTHLY_TAX,
                social_insurance=MONTHLY_SOCIAL,
                total_deductions=MONTHLY_TAX + MONTHLY_SOCIAL,
                net_pay=MONTHLY_GROSS - MONTHLY_TAX - MONTHLY_SOCIAL,
                status="confirmed",
            )
        )
    await db_session.flush()

    return {
        "company_id": co.company_id,
        "employee_id": emp.employee_id,
        "token": create_access_token(str(user.user_id)),
    }


async def _calculate(api, setup, dependents: int = 0):
    return await api.post(
        "/api/v1/year-end/calculate",
        json={
            "company_id": str(setup["company_id"]),
            "adjustment_year": YEAR,
            "dependents_override": {str(setup["employee_id"]): dependents},
        },
        headers={"Authorization": f"Bearer {setup['token']}"},
    )


def _expected_year_tax(dependents: int) -> Decimal:
    """検証済みサービスから期待値を組み立てる（実装の写経にしない）。"""
    gross = MONTHLY_GROSS * 12
    salary_income = gross - SalaryIncomeDeductionService.compute(gross)
    deductions = (
        MONTHLY_SOCIAL * 12 + basic_deduction(salary_income) + dependent_deduction(dependents)
    )
    return YearEndAdjustmentService.compute(
        annual_gross_salary=gross,
        total_income_deductions=deductions,
        withheld_tax_total=MONTHLY_TAX * 12,
    ).year_tax


async def test_annual_tax_subtracts_income_deductions(api, setup):
    """給与収入ではなく課税給与所得に課税すること。"""
    res = await _calculate(api, setup)

    assert res.status_code == 200, res.text
    record = res.json()[0]
    assert Decimal(record["estimated_annual_tax"]) == _expected_year_tax(0)


async def test_old_behaviour_would_have_overtaxed(api, setup):
    """控除を無視した旧実装の税額とは一致しないこと（桁違いに大きかった）。"""
    res = await _calculate(api, setup)
    actual = Decimal(res.json()[0]["estimated_annual_tax"])

    gross = MONTHLY_GROSS * 12
    old = (gross * Decimal("0.20") - Decimal("427500")).quantize(Decimal("1"))
    assert actual < old / 2, f"控除が効いていない（実測 {actual} / 旧実装 {old}）"


async def test_dependents_reduce_the_tax(api, setup):
    """扶養親族が増えれば年税額は下がること。"""
    none = Decimal((await _calculate(api, setup, 0)).json()[0]["estimated_annual_tax"])
    two = Decimal((await _calculate(api, setup, 2)).json()[0]["estimated_annual_tax"])

    assert two < none
    assert two == _expected_year_tax(2)


async def test_refund_when_withheld_exceeds_the_year_tax(api, setup):
    """源泉徴収済みが年税額を上回れば還付（正の調整額）になること。"""
    res = await _calculate(api, setup)
    record = res.json()[0]

    withheld = MONTHLY_TAX * 12
    expected = withheld - _expected_year_tax(0)
    assert Decimal(record["adjustment_amount"]) == expected


async def test_dependent_deduction_is_recorded(api, setup):
    """記録される扶養控除額が控除サービスと一致すること。"""
    record = (await _calculate(api, setup, 2)).json()[0]

    assert Decimal(record["dependent_deduction"]) == dependent_deduction(2)
