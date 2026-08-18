import contextlib
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.business_time import business_today
from app.core.csv_export import csv_line
from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission, verified_company_id
from app.core.rbac import Permission
from app.core.tenant_scope import assert_company_access
from app.models.models import BonusRecord, Company, Employee
from app.schemas.schemas import BonusCalculateRequest, BonusListResponse, BonusRecordResponse, NotificationCreate
from app.services.auto_journal import generate_bonus_journal
from app.services.notification_service import create_notification
from app.services.social_insurance import (
    DEFAULT_CARE_INSURANCE_RATE,
    DEFAULT_HEALTH_INSURANCE_RATE,
    SocialInsurancePremiumService,
    care_insurance_applicable,
    standard_bonus_amounts,
)

BONUS_TERM_LABELS = {
    "summer": "夏季賞与",
    "winter": "冬季賞与",
    "yearend": "年末賞与",
    "other": "その他",
}

router = APIRouter()


# 賞与の源泉所得税は「賞与に対する源泉徴収税額の算出率表」を、前月の社会保険料等
# 控除後給与と扶養親族等の数で引く必要がある。扶養親族等の数を保持していないため
# 算出率を決められず、概算のままになっている。
# 社会保険料は標準賞与額から正しく計算できるので、概算はこの1項目だけ。
ESTIMATED_BONUS_FIELDS = ("income_tax",)

BONUS_ESTIMATE_NOTICE = (
    "賞与の源泉所得税は概算です（算出率表・前月給与・扶養親族等の数が未対応）。"
    "納付額の算出にはそのまま使用しないでください。"
)


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
        estimated_fields=list(ESTIMATED_BONUS_FIELDS),
        estimate_notice=BONUS_ESTIMATE_NOTICE,
    )


def _estimate_bonus_tax(gross: Decimal) -> Decimal:
    """賞与の源泉所得税の概算。算出率表によらない（ESTIMATED_BONUS_FIELDS 参照）。"""
    if gross <= 0:
        return Decimal("0")
    return (gross * Decimal("0.1021")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


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
    await assert_company_access(db, current_user, payload.company_id)
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

    company = (
        await db.execute(select(Company).where(Company.company_id == payload.company_id))
    ).scalar_one()

    # 健康保険の標準賞与額は年度累計573万円が上限。同一年度に支給済みの賞与を集計する
    # （夏季・冬季とも同じ年度に入るため bonus_year を年度として扱う）。
    paid_rows = await db.execute(
        select(BonusRecord.employee_id, func.sum(BonusRecord.bonus_amount))
        .where(
            BonusRecord.company_id == payload.company_id,
            BonusRecord.bonus_year == payload.bonus_year,
        )
        .group_by(BonusRecord.employee_id)
    )
    paid_health_bonus_by_employee = {row[0]: row[1] or Decimal("0") for row in paid_rows}
    # 介護保険の要否は支給日時点の満年齢で判定する。
    bonus_paid_on = business_today()

    records: list[BonusRecord] = []
    for emp in employees:
        factor = payload.performance_factors.get(emp.employee_id, Decimal("1.00"))
        bonus_amount = (emp.base_salary * payload.bonus_base_months * factor).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        income_tax = _estimate_bonus_tax(bonus_amount)
        # 社会保険料は標準賞与額（1,000円未満切捨・年度/1回あたりの上限あり）で決まる。
        # 賞与額に率を直接掛けると、上限も切り捨ても効かず高額賞与で過大徴収になる。
        paid_health_bonus = paid_health_bonus_by_employee.get(emp.employee_id, Decimal("0"))
        standard = standard_bonus_amounts(bonus_amount, paid_health_bonus)
        social_ins = SocialInsurancePremiumService.compute_bonus(
            health_standard_bonus=standard.health,
            pension_standard_bonus=standard.pension,
            health_rate=company.health_insurance_rate
            if company.health_insurance_rate is not None
            else DEFAULT_HEALTH_INSURANCE_RATE,
            care_rate=company.care_insurance_rate
            if company.care_insurance_rate is not None
            else DEFAULT_CARE_INSURANCE_RATE,
            care_applicable=care_insurance_applicable(emp.birth_date, bonus_paid_on),
        ).total_employee
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


@router.get("/records", response_model=BonusListResponse)
async def list_bonus_records(
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
    bonus_year: int = Query(...),
    bonus_term: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> BonusListResponse:
    count_result = await db.execute(
        select(func.count()).select_from(BonusRecord).where(
            BonusRecord.company_id == company_id,
            BonusRecord.bonus_year == bonus_year,
            BonusRecord.bonus_term == bonus_term,
        )
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(BonusRecord, Employee.employee_name)
        .join(Employee, BonusRecord.employee_id == Employee.employee_id)
        .where(
            BonusRecord.company_id == company_id,
            BonusRecord.bonus_year == bonus_year,
            BonusRecord.bonus_term == bonus_term,
        )
        .order_by(Employee.employee_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()
    items = [_to_bonus_response(rec, name) for rec, name in rows]
    return BonusListResponse(items=items, total=total, page=page, page_size=page_size)


VALID_BONUS_TRANSITIONS: dict[str, set[str]] = {
    "calculated": {"approved", "rejected"},
    "approved": {"paid"},
    "rejected": {"calculated"},
    "paid": set(),
}


@router.post("/records/batch-transition", response_model=list[BonusRecordResponse])
async def batch_transition_bonus(
    company_id: UUID = Depends(verified_company_id),  # noqa: B008
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

    # Notify on batch transition
    labels = {"approved": "承認", "rejected": "差戻し", "paid": "支払完了"}
    with contextlib.suppress(Exception):
        await create_notification(db, current_user.tenant_id, NotificationCreate(
            company_id=company_id,
            category="payroll",
            priority="high" if action == "paid" else "normal",
            title=f"賞与 {bonus_year}年{bonus_term} 一括{labels[action]}",
            body=f"{len(updated)}件の賞与レコードを{labels[action]}しました。",
            action_url="/bonus",
        ))

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

    # 氏名・部署は自由入力のため、カンマ・改行・数式記号を含みうる。csv_lineで無害化する。
    rows: list[list[object]] = [
        ["項目", "内容"],
        ["従業員コード", emp_code],
        ["従業員名", emp_name],
        ["部署", dept or ""],
        ["対象年度", f"{rec.bonus_year}年"],
        ["賞与区分", term_label],
        [],
        ["支給項目", "金額"],
        ["基準月数", f"{rec.bonus_base_months}ヶ月"],
        ["業績係数", rec.performance_factor],
        ["賞与額", rec.bonus_amount],
        [],
        ["控除項目", "金額"],
        ["源泉所得税", rec.income_tax],
        ["社会保険料", rec.social_insurance],
        ["控除合計", rec.total_deductions],
        [],
        ["差引支給額", rec.net_pay],
        ["ステータス", rec.status],
    ]

    return "\n".join(csv_line(row) for row in rows)
