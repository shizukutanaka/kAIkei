from contextlib import suppress
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.csv_export import csv_line
from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission, verified_company_id
from app.core.rbac import Permission
from app.core.tenant_scope import assert_company_access
from app.models.models import BonusRecord, Employee, PayrollRecord, YearEndAdjustment
from app.schemas.schemas import (
    NotificationCreate,
    YearEndAdjustmentRequest,
    YearEndAdjustmentResponse,
    YearEndListResponse,
)
from app.services.income_deduction import basic_deduction, dependent_deduction
from app.services.notification_service import create_notification
from app.services.salary_deduction import SalaryIncomeDeductionService
from app.services.year_end_adjustment import YearEndAdjustmentService

router = APIRouter()


# 年税額の計算自体は法定どおり（給与所得控除→速算表→復興特別所得税）だが、
# 比較対象の「徴収済み税額」は月次の源泉所得税に由来し、それが概算のままである。
# したがって還付・追徴の金額も概算になる。月次が法定計算に対応すれば解消する。
ESTIMATED_YEAR_END_FIELDS = ("withholding_tax_total", "adjustment_amount")

YEAR_END_ESTIMATE_NOTICE = (
    "還付・追徴額は概算です（毎月の源泉所得税が概算のため）。"
    "実際の精算にはそのまま使用しないでください。"
)


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
        estimated_fields=list(ESTIMATED_YEAR_END_FIELDS),
        estimate_notice=YEAR_END_ESTIMATE_NOTICE,
    )


@router.post("/calculate", response_model=list[YearEndAdjustmentResponse])
async def calculate_year_end_adjustment(
    payload: YearEndAdjustmentRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[YearEndAdjustmentResponse]:
    """年末調整を計算する。"""
    await assert_company_access(db, current_user, payload.company_id)
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

        # 課税対象は「給与収入」ではなく、給与所得控除・社会保険料控除・基礎控除・
        # 扶養控除を差し引いた課税給与所得金額。控除を引かずに税率を掛けると
        # 税額が数倍になり、還付すべき人に追徴が出る。
        salary_income = total_gross - SalaryIncomeDeductionService.compute(total_gross)
        dependent_deduction_amount = dependent_deduction(dependents)
        deductions = total_social_ins + basic_deduction(salary_income) + dependent_deduction_amount
        adjustment = YearEndAdjustmentService.compute(
            annual_gross_salary=total_gross,
            total_income_deductions=deductions,
            withheld_tax_total=total_withholding,
        )
        estimated_tax = adjustment.year_tax
        # 還付は正、追徴は負で保持する（従来の符号を踏襲）。
        adjustment_amount = adjustment.refund - adjustment.additional_collection

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
            dependent_deduction=dependent_deduction_amount,
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
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    adjustment_year: int = Query(...),  # noqa: B008
    page: int = Query(1, ge=1),  # noqa: B008
    page_size: int = Query(50, ge=1, le=200),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
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


@router.get("/salary-income-deduction")
async def get_salary_income_deduction(
    gross_salary: Decimal = Query(..., description="給与等の収入金額"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> dict[str, Decimal]:
    try:
        salary_income_deduction = SalaryIncomeDeductionService.compute(gross_salary)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "gross_salary": gross_salary,
        "salary_income_deduction": salary_income_deduction,
        "salary_income": gross_salary - salary_income_deduction,
    }


VALID_YE_TRANSITIONS: dict[str, set[str]] = {
    "calculated": {"approved"},
    "approved": set(),
}


@router.post("/records/batch-transition", response_model=list[YearEndAdjustmentResponse])
async def batch_transition_year_end(
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    adjustment_year: int = Query(...),  # noqa: B008
    action: str = Query(..., description="approved"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.PAYROLL_APPROVE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
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

    # Notify on batch transition
    with suppress(Exception):
        await create_notification(
            db,
            current_user.tenant_id,
            NotificationCreate(
                company_id=company_id,
                category="tax",
                priority="high",
                title=f"年末調整 {adjustment_year}年 一括確定",
                body=f"{len(updated)}件の年末調整を確定しました。",
                action_url="/year-end",
            ),
        )

    await db.commit()
    return updated


@router.get("/export/{adjustment_id}", response_class=PlainTextResponse)
async def export_year_end_slip(
    adjustment_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
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

    # 氏名・部署は自由入力のため、カンマ・改行・数式記号を含みうる。csv_lineで無害化する。
    rows: list[list[object]] = [
        ["項目", "内容"],
        ["従業員コード", emp_code],
        ["従業員名", emp_name],
        ["部署", dept or ""],
        ["対象年度", f"{rec.adjustment_year}年"],
        [],
        ["年間収入", "金額"],
        ["年間給与", rec.annual_salary],
        ["年間賞与", rec.annual_bonus],
        ["課税対象額", rec.total_gross],
        [],
        ["税額", "金額"],
        ["源泉徴収額合計", rec.withholding_tax_total],
        ["推定年税額", rec.estimated_annual_tax],
        ["社会保険料合計", rec.social_insurance_total],
        [],
        ["扶養控除", "内容"],
        ["扶養親族数", f"{rec.dependents}人"],
        ["扶養控除額", rec.dependent_deduction],
        [],
        ["調整額", f"{rec.adjustment_amount}({adjustment_sign})"],
        ["ステータス", rec.status],
    ]

    return "\n".join(csv_line(row) for row in rows)
