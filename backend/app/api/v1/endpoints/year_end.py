from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Employee, PayrollRecord, BonusRecord, YearEndAdjustment
from app.schemas.schemas import YearEndAdjustmentRequest, YearEndAdjustmentResponse, YearEndListResponse

router = APIRouter()


def _to_response(rec: YearEndAdjustment, emp_name: str | None = None) -> YearEndAdjustmentResponse:
    return YearEndAdjustmentResponse(
        adjustment_id=rec.adjustment_id,
        employee_id=rec.employee_id,
        company_id=rec.company_id,
        adjustment_year=rec.adjustment_year,
        annual_salary=rec.annual_salary,
        annual_bonus=rec.annual_bonus,
        total_gross=rec.total_gross,
        withholding_tax_total=rec.withholding_tax_total,
        estimated_annual_tax=rec.estimated_annual_tax,
        social_insurance_total=rec.social_insurance_total,
        dependents=rec.dependents,
        dependent_deduction=rec.dependent_deduction,
        adjustment_amount=rec.adjustment_amount,
        status=rec.status,
        employee_name=emp_name,
    )


def _calc_annual_tax(gross: Decimal, dependents: int) -> Decimal:
    """簡易年間所得税計算（累進税率 + 扶養控除）。"""
    dependent_deduction = Decimal(str(dependents * 380000))
    taxable = gross - dependent_deduction
    if taxable <= 0:
        return Decimal("0")
    if taxable <= 1950000:
        rate = Decimal("0.05")
        deduction = Decimal("0")
    elif taxable <= 3300000:
        rate = Decimal("0.10")
        deduction = Decimal("97500")
    elif taxable <= 6945000:
        rate = Decimal("0.20")
        deduction = Decimal("427500")
    elif taxable <= 9000000:
        rate = Decimal("0.23")
        deduction = Decimal("636000")
    elif taxable <= 18000000:
        rate = Decimal("0.33")
        deduction = Decimal("1536000")
    elif taxable <= 40000000:
        rate = Decimal("0.40")
        deduction = Decimal("2796000")
    else:
        rate = Decimal("0.45")
        deduction = Decimal("4796000")
    tax = (taxable * rate - deduction).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(tax, Decimal("0"))


@router.post("/calculate", response_model=list[YearEndAdjustmentResponse])
async def calculate_year_end_adjustment(
    payload: YearEndAdjustmentRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> list[YearEndAdjustmentResponse]:
    """年末調整を計算する。"""
    await db.execute(
        delete(YearEndAdjustment).where(
            YearEndAdjustment.company_id == payload.company_id,
            YearEndAdjustment.adjustment_year == payload.adjustment_year,
        )
    )

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

    records: list[YearEndAdjustment] = []
    for emp in employees:
        # 年間給与集計
        payroll_result = await db.execute(
            select(
                func.coalesce(func.sum(PayrollRecord.total_gross), Decimal("0")),
                func.coalesce(func.sum(PayrollRecord.income_tax), Decimal("0")),
                func.coalesce(func.sum(PayrollRecord.social_insurance), Decimal("0")),
            ).where(
                PayrollRecord.employee_id == emp.employee_id,
                PayrollRecord.payroll_year == payload.adjustment_year,
            )
        )
        annual_salary, withholding_tax, social_ins_total = payroll_result.one()

        # 年間賞与集計
        bonus_result = await db.execute(
            select(
                func.coalesce(func.sum(BonusRecord.bonus_amount), Decimal("0")),
                func.coalesce(func.sum(BonusRecord.income_tax), Decimal("0")),
                func.coalesce(func.sum(BonusRecord.social_insurance), Decimal("0")),
            ).where(
                BonusRecord.employee_id == emp.employee_id,
                BonusRecord.bonus_year == payload.adjustment_year,
            )
        )
        annual_bonus, bonus_tax, bonus_social_ins = bonus_result.one()

        total_gross = annual_salary + annual_bonus
        total_withholding = withholding_tax + bonus_tax
        total_social_ins = social_ins_total + bonus_social_ins

        dependents = payload.dependents_override.get(emp.employee_id, 0)
        dependent_deduction = Decimal(str(dependents * 380000))
        estimated_tax = _calc_annual_tax(total_gross, dependents)
        adjustment_amount = (total_withholding - estimated_tax).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )

        rec = YearEndAdjustment(
            employee_id=emp.employee_id,
            company_id=payload.company_id,
            adjustment_year=payload.adjustment_year,
            annual_salary=annual_salary,
            annual_bonus=annual_bonus,
            total_gross=total_gross,
            withholding_tax_total=total_withholding,
            estimated_annual_tax=estimated_tax,
            social_insurance_total=total_social_ins,
            dependents=dependents,
            dependent_deduction=dependent_deduction,
            adjustment_amount=adjustment_amount,
            status="calculated",
        )
        db.add(rec)
        records.append(rec)

    await db.commit()
    for rec in records:
        await db.refresh(rec)

    # 従業員名を一括取得
    emp_ids = {r.employee_id for r in records}
    if emp_ids:
        name_result = await db.execute(
            select(Employee.employee_id, Employee.employee_name).where(Employee.employee_id.in_(emp_ids))
        )
        name_map = dict(name_result.all())
    else:
        name_map = {}

    return [_to_response(r, name_map.get(r.employee_id)) for r in records]


@router.get("/records", response_model=YearEndListResponse)
async def list_year_end_adjustments(
    company_id: UUID = Query(...),
    adjustment_year: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> YearEndListResponse:
    base_query = (
        select(YearEndAdjustment, Employee.employee_name)
        .join(Employee, YearEndAdjustment.employee_id == Employee.employee_id)
        .where(
            YearEndAdjustment.company_id == company_id,
            YearEndAdjustment.adjustment_year == adjustment_year,
        )
    )
    count_result = await db.execute(
        select(func.count()).select_from(YearEndAdjustment).where(
            YearEndAdjustment.company_id == company_id,
            YearEndAdjustment.adjustment_year == adjustment_year,
        )
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        base_query.order_by(Employee.employee_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()
    items = [_to_response(rec, name) for rec, name in rows]
    return YearEndListResponse(items=items, total=total, page=page, page_size=page_size)


VALID_YE_TRANSITIONS: dict[str, set[str]] = {
    "calculated": {"approved"},
    "approved": set(),
}


@router.post("/records/batch-transition", response_model=list[YearEndAdjustmentResponse])
async def batch_transition_year_end(
    company_id: UUID = Query(...),
    adjustment_year: int = Query(...),
    action: str = Query(..., description="approved"),
    current_user: CurrentUser = Depends(require_permission(Permission.PAYROLL_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> list[YearEndAdjustmentResponse]:
    """年末調整のステータスを一括遷移させる。"""
    if action not in {"approved"}:
        raise HTTPException(status_code=400, detail=f"無効なアクション: {action}")

    result = await db.execute(
        select(YearEndAdjustment, Employee.employee_name)
        .join(Employee, YearEndAdjustment.employee_id == Employee.employee_id)
        .where(
            YearEndAdjustment.company_id == company_id,
            YearEndAdjustment.adjustment_year == adjustment_year,
        )
        .order_by(Employee.employee_code)
    )
    rows = result.all()
    if not rows:
        raise HTTPException(status_code=404, detail="該当の年末調整レコードがありません")

    allowed = VALID_YE_TRANSITIONS.get(rows[0][0].status, set())
    if action not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"現在のステータス「{rows[0][0].status}」から「{action}」への遷移は許可されていません",
        )

    updated: list[YearEndAdjustmentResponse] = []
    for rec, emp_name in rows:
        rec.status = action
        updated.append(_to_response(rec, emp_name))

    await db.commit()
    return updated


@router.get("/export/{adjustment_id}", response_class=PlainTextResponse)
async def export_year_end_slip(
    adjustment_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> str:
    """年末調整明細をCSV形式で出力する。"""
    result = await db.execute(
        select(YearEndAdjustment, Employee.employee_name, Employee.employee_code, Employee.department)
        .join(Employee, YearEndAdjustment.employee_id == Employee.employee_id)
        .where(YearEndAdjustment.adjustment_id == adjustment_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="年末調整レコードが見つかりません")

    rec, emp_name, emp_code, dept = row
    adjustment_sign = "還付" if rec.adjustment_amount >= 0 else "追加徴収"

    lines = [
        "項目,内容",
        f"従業員コード,{emp_code}",
        f"従業員名,{emp_name}",
        f"部署,{dept or ''}",
        f"対象年度,{rec.adjustment_year}年",
        "",
        "年間収入,金額",
        f"年間給与,{rec.annual_salary}",
        f"年間賞与,{rec.annual_bonus}",
        f"課税対象額,{rec.total_gross}",
        "",
        "税額,金額",
        f"源泉徴収額合計,{rec.withholding_tax_total}",
        f"推定年税額,{rec.estimated_annual_tax}",
        f"社会保険料合計,{rec.social_insurance_total}",
        "",
        "扶養控除,内容",
        f"扶養親族数,{rec.dependents}人",
        f"扶養控除額,{rec.dependent_deduction}",
        "",
        f"調整額,{rec.adjustment_amount}({adjustment_sign})",
        f"ステータス,{rec.status}",
    ]

    return "\n".join(lines)
