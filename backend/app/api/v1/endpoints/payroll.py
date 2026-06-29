from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Employee, PayrollRecord
from app.schemas.schemas import (
    EmployeeCreate,
    EmployeeResponse,
    PayrollCalculateRequest,
    PayrollRecordResponse,
)

router = APIRouter()


def _to_employee_response(emp: Employee) -> EmployeeResponse:
    return EmployeeResponse(
        employee_id=emp.employee_id,
        company_id=emp.company_id,
        employee_code=emp.employee_code,
        employee_name=emp.employee_name,
        department=emp.department,
        position=emp.position,
        employment_type=emp.employment_type,
        base_salary=emp.base_salary,
        hourly_rate=emp.hourly_rate,
        hire_date=emp.hire_date,
        termination_date=emp.termination_date,
        is_active=emp.is_active,
    )


def _to_payroll_response(rec: PayrollRecord, emp_name: str | None = None) -> PayrollRecordResponse:
    return PayrollRecordResponse(
        payroll_id=rec.payroll_id,
        employee_id=rec.employee_id,
        company_id=rec.company_id,
        payroll_year=rec.payroll_year,
        payroll_month=rec.payroll_month,
        base_salary=rec.base_salary,
        overtime_hours=rec.overtime_hours,
        overtime_pay=rec.overtime_pay,
        total_gross=rec.total_gross,
        income_tax=rec.income_tax,
        social_insurance=rec.social_insurance,
        total_deductions=rec.total_deductions,
        net_pay=rec.net_pay,
        status=rec.status,
        employee_name=emp_name,
    )


def _calc_income_tax(gross: Decimal) -> Decimal:
    """簡易源泉所得税計算（月額表の近似）。"""
    if gross <= 0:
        return Decimal("0")
    # 簡易税率: 5% (実際の源泉所得税表は複雑)
    return (gross * Decimal("0.05")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _calc_social_insurance(gross: Decimal) -> Decimal:
    """簡易社会保険料計算（健康保険+厚生年金）。"""
    if gross <= 0:
        return Decimal("0")
    # 簡易: 総額の約15%
    return (gross * Decimal("0.15")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


# --- Employee endpoints ---

@router.get("/employees", response_model=list[EmployeeResponse])
async def list_employees(
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[EmployeeResponse]:
    result = await db.execute(
        select(Employee).where(
            Employee.company_id == company_id,
            Employee.is_deleted == False,  # noqa: E712
        ).order_by(Employee.employee_code)
    )
    employees = result.scalars().all()
    return [_to_employee_response(e) for e in employees]


@router.post("/employees", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: EmployeeCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    existing = await db.execute(
        select(Employee).where(
            Employee.company_id == payload.company_id,
            Employee.employee_code == payload.employee_code,
            Employee.is_deleted == False,  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="この従業員コードは既に存在します")

    emp = Employee(
        company_id=payload.company_id,
        employee_code=payload.employee_code,
        employee_name=payload.employee_name,
        department=payload.department,
        position=payload.position,
        employment_type=payload.employment_type,
        base_salary=payload.base_salary,
        hourly_rate=payload.hourly_rate,
        hire_date=payload.hire_date,
    )
    db.add(emp)
    await db.commit()
    await db.refresh(emp)
    return _to_employee_response(emp)


@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_DELETE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Employee).where(
            Employee.employee_id == employee_id,
            Employee.is_deleted == False,  # noqa: E712
        )
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="従業員が見つかりません")
    emp.is_deleted = True
    emp.is_active = False
    await db.commit()


# --- Payroll endpoints ---

@router.post("/calculate", response_model=list[PayrollRecordResponse])
async def calculate_payroll(
    payload: PayrollCalculateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> list[PayrollRecordResponse]:
    """月次給与計算を実行する。"""
    # 該当月の既存レコードを削除（再計算用）
    await db.execute(
        delete(PayrollRecord).where(
            PayrollRecord.company_id == payload.company_id,
            PayrollRecord.payroll_year == payload.payroll_year,
            PayrollRecord.payroll_month == payload.payroll_month,
        )
    )

    # アクティブな従業員を取得
    result = await db.execute(
        select(Employee).where(
            Employee.company_id == payload.company_id,
            Employee.is_active == True,  # noqa: E712
            Employee.is_deleted == False,  # noqa: E712
        ).order_by(Employee.employee_code)
    )
    employees = result.scalars().all()

    if not employees:
        raise HTTPException(status_code=404, detail="アクティブな従業員がいません")

    records: list[PayrollRecord] = []
    for emp in employees:
        ot_hours = payload.overtime_hours.get(emp.employee_id, Decimal("0"))
        ot_pay = (emp.hourly_rate * ot_hours * Decimal("1.25")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        total_gross = emp.base_salary + ot_pay
        income_tax = _calc_income_tax(total_gross)
        social_ins = _calc_social_insurance(total_gross)
        total_deductions = income_tax + social_ins
        net_pay = total_gross - total_deductions

        rec = PayrollRecord(
            employee_id=emp.employee_id,
            company_id=payload.company_id,
            payroll_year=payload.payroll_year,
            payroll_month=payload.payroll_month,
            base_salary=emp.base_salary,
            overtime_hours=ot_hours,
            overtime_pay=ot_pay,
            total_gross=total_gross,
            income_tax=income_tax,
            social_insurance=social_ins,
            total_deductions=total_deductions,
            net_pay=net_pay,
            status="calculated",
        )
        db.add(rec)
        records.append(rec)

    await db.commit()
    for rec in records:
        await db.refresh(rec)

    return [_to_payroll_response(r) for r in records]


@router.get("/records", response_model=list[PayrollRecordResponse])
async def list_payroll_records(
    company_id: UUID = Query(...),
    payroll_year: int = Query(...),
    payroll_month: int = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[PayrollRecordResponse]:
    result = await db.execute(
        select(PayrollRecord, Employee.employee_name)
        .join(Employee, PayrollRecord.employee_id == Employee.employee_id)
        .where(
            PayrollRecord.company_id == company_id,
            PayrollRecord.payroll_year == payroll_year,
            PayrollRecord.payroll_month == payroll_month,
        )
        .order_by(Employee.employee_code)
    )
    rows = result.all()
    return [_to_payroll_response(rec, name) for rec, name in rows]


@router.get("/payslip/{payroll_id}", response_class=PlainTextResponse)
async def export_payslip(
    payroll_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> str:
    """給与明細をCSV形式で出力する。"""
    result = await db.execute(
        select(PayrollRecord, Employee.employee_name, Employee.employee_code, Employee.department)
        .join(Employee, PayrollRecord.employee_id == Employee.employee_id)
        .where(PayrollRecord.payroll_id == payroll_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="給与レコードが見つかりません")

    rec, emp_name, emp_code, dept = row

    lines = [
        "項目,内容",
        f"従業員コード,{emp_code}",
        f"従業員名,{emp_name}",
        f"部署,{dept or ''}",
        f"対象年月,{rec.payroll_year}年{rec.payroll_month}月",
        "",
        "支給項目,金額",
        f"基本給,{rec.base_salary}",
        f"残業時間,{rec.overtime_hours}h",
        f"残業代,{rec.overtime_pay}",
        f"総支給額,{rec.total_gross}",
        "",
        "控除項目,金額",
        f"源泉所得税,{rec.income_tax}",
        f"社会保険料,{rec.social_insurance}",
        f"控除合計,{rec.total_deductions}",
        "",
        f"差引支給額,{rec.net_pay}",
        f"ステータス,{rec.status}",
    ]

    return "\n".join(lines)
