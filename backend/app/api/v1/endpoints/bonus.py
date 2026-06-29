from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Employee, BonusRecord
from app.schemas.schemas import BonusCalculateRequest, BonusRecordResponse
from app.services.auto_journal import generate_bonus_journal

BONUS_TERM_LABELS = {
    "summer": "夏季賞与",
    "winter": "冬季賞与",
    "yearend": "年末賞与",
    "other": "その他",
}

router = APIRouter()


def _to_bonus_response(rec: BonusRecord, emp_name: str | None = None) -> BonusRecordResponse:
    return BonusRecordResponse(
        bonus_id=rec.bonus_id,
        employee_id=rec.employee_id,
        company_id=rec.company_id,
        bonus_year=rec.bonus_year,
        bonus_term=rec.bonus_term,
        bonus_amount=rec.bonus_amount,
        bonus_base_months=rec.bonus_base_months,
        performance_factor=rec.performance_factor,
        income_tax=rec.income_tax,
        social_insurance=rec.social_insurance,
        total_deductions=rec.total_deductions,
        net_pay=rec.net_pay,
        status=rec.status,
        employee_name=emp_name,
    )


def _calc_bonus_tax(gross: Decimal) -> Decimal:
    """賞与の源泉所得税（簡易: 賞与額の10.21%を基準に一律計算）。"""
    if gross <= 0:
        return Decimal("0")
    return (gross * Decimal("0.1021")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _calc_bonus_social_insurance(gross: Decimal) -> Decimal:
    """賞与の社会保険料（簡易: 賞与額の15%）。"""
    if gross <= 0:
        return Decimal("0")
    return (gross * Decimal("0.15")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


BONUS_TERM_LABELS = {
    "summer": "夏季賞与",
    "winter": "冬季賞与",
    "yearend": "年末賞与",
    "other": "その他",
}


@router.post("/calculate", response_model=list[BonusRecordResponse])
async def calculate_bonus(
    payload: BonusCalculateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> list[BonusRecordResponse]:
    """賞与計算を実行する。"""
    valid_terms = {"summer", "winter", "yearend", "other"}
    if payload.bonus_term not in valid_terms:
        raise HTTPException(
            status_code=422,
            detail=f"無効な賞与区分: {payload.bonus_term}。有効な値: {', '.join(sorted(valid_terms))}",
        )

    await db.execute(
        delete(BonusRecord).where(
            BonusRecord.company_id == payload.company_id,
            BonusRecord.bonus_year == payload.bonus_year,
            BonusRecord.bonus_term == payload.bonus_term,
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

    records: list[BonusRecord] = []
    for emp in employees:
        factor = payload.performance_factors.get(emp.employee_id, Decimal("1.00"))
        bonus_amount = (emp.base_salary * payload.bonus_base_months * factor).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        income_tax = _calc_bonus_tax(bonus_amount)
        social_ins = _calc_bonus_social_insurance(bonus_amount)
        total_deductions = income_tax + social_ins
        net_pay = bonus_amount - total_deductions

        rec = BonusRecord(
            employee_id=emp.employee_id,
            company_id=payload.company_id,
            bonus_year=payload.bonus_year,
            bonus_term=payload.bonus_term,
            bonus_amount=bonus_amount,
            bonus_base_months=payload.bonus_base_months,
            performance_factor=factor,
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

    return [_to_bonus_response(r) for r in records]


@router.get("/records", response_model=list[BonusRecordResponse])
async def list_bonus_records(
    company_id: UUID = Query(...),
    bonus_year: int = Query(...),
    bonus_term: str = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[BonusRecordResponse]:
    result = await db.execute(
        select(BonusRecord, Employee.employee_name)
        .join(Employee, BonusRecord.employee_id == Employee.employee_id)
        .where(
            BonusRecord.company_id == company_id,
            BonusRecord.bonus_year == bonus_year,
            BonusRecord.bonus_term == bonus_term,
        )
        .order_by(Employee.employee_code)
    )
    rows = result.all()
    return [_to_bonus_response(rec, name) for rec, name in rows]


VALID_BONUS_TRANSITIONS: dict[str, set[str]] = {
    "calculated": {"approved", "rejected"},
    "approved": {"paid"},
    "rejected": {"calculated"},
    "paid": set(),
}


@router.post("/records/batch-transition", response_model=list[BonusRecordResponse])
async def batch_transition_bonus(
    company_id: UUID = Query(...),
    bonus_year: int = Query(...),
    bonus_term: str = Query(...),
    action: str = Query(..., description="approved, rejected, or paid"),
    current_user: CurrentUser = Depends(require_permission(Permission.PAYROLL_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> list[BonusRecordResponse]:
    """指定タームの全賞与レコードのステータスを一括遷移させる。"""
    valid_actions = {"approved", "rejected", "paid"}
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"無効なアクション: {action}")

    result = await db.execute(
        select(BonusRecord, Employee.employee_name)
        .join(Employee, BonusRecord.employee_id == Employee.employee_id)
        .where(
            BonusRecord.company_id == company_id,
            BonusRecord.bonus_year == bonus_year,
            BonusRecord.bonus_term == bonus_term,
        )
        .order_by(Employee.employee_code)
    )
    rows = result.all()
    if not rows:
        raise HTTPException(status_code=404, detail="該当の賞与レコードがありません")

    allowed = VALID_BONUS_TRANSITIONS.get(rows[0][0].status, set())
    if action not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"現在のステータス「{rows[0][0].status}」から「{action}」への遷移は許可されていません",
        )

    updated: list[BonusRecordResponse] = []
    total_gross_sum = Decimal("0")
    total_deductions_sum = Decimal("0")
    net_pay_sum = Decimal("0")
    for rec, emp_name in rows:
        rec.status = action
        total_gross_sum += rec.bonus_amount
        total_deductions_sum += rec.total_deductions
        net_pay_sum += rec.net_pay
        updated.append(_to_bonus_response(rec, emp_name))

    # Auto-generate bonus journal on batch "paid" transition
    if action == "paid":
        try:
            await generate_bonus_journal(
                db,
                company_id=company_id,
                bonus_year=bonus_year,
                bonus_term=bonus_term,
                total_gross=total_gross_sum,
                total_deductions=total_deductions_sum,
                net_pay=net_pay_sum,
                created_by=current_user.user_id,
            )
        except ValueError:
            pass  # Account not found — skip auto-journal

    await db.commit()
    return updated


@router.get("/export/{bonus_id}", response_class=PlainTextResponse)
async def export_bonus_slip(
    bonus_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> str:
    """賞与明細をCSV形式で出力する。"""
    result = await db.execute(
        select(BonusRecord, Employee.employee_name, Employee.employee_code, Employee.department)
        .join(Employee, BonusRecord.employee_id == Employee.employee_id)
        .where(BonusRecord.bonus_id == bonus_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="賞与レコードが見つかりません")

    rec, emp_name, emp_code, dept = row
    term_label = BONUS_TERM_LABELS.get(rec.bonus_term, rec.bonus_term)

    lines = [
        "項目,内容",
        f"従業員コード,{emp_code}",
        f"従業員名,{emp_name}",
        f"部署,{dept or ''}",
        f"対象年度,{rec.bonus_year}年",
        f"賞与区分,{term_label}",
        "",
        "支給項目,金額",
        f"基準月数,{rec.bonus_base_months}ヶ月",
        f"業績係数,{rec.performance_factor}",
        f"賞与額,{rec.bonus_amount}",
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
