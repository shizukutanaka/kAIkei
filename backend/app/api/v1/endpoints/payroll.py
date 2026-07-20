# ruff: noqa: B008, I001
from contextlib import suppress
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Employee, PayrollRecord
from app.schemas.schemas import (
    EmployeeCreate,
    EmployeeListResponse,
    EmployeeResponse,
    LaborInsuranceEmployeeResponse,
    LaborInsuranceSummaryResponse,
    LaborInsuranceAnnualUpdateRequest,
    NotificationCreate,
    BonusExportRequest,
    MonthlyRevisionExportRequest,
    PayrollCalculateRequest,
    PayrollListResponse,
    PayrollRecordResponse,
    BonusEmploymentInsuranceResponse,
    BonusWithholdingTaxResponse,
    BonusNetPayResponse,
    CommuteAllowanceResponse,
    PaidLeaveGrantResponse,
    OvertimeLimitCheckRequest,
    OvertimeLimitCheckResponse,
    RetirementIncomeTaxResponse,
    MonthlyPayslipResponse,
    MinimumWageCheckResponse,
    DependentEligibilityResponse,
    SocialInsuranceExemptionResponse,
    YearEndAdjustmentCalcResponse,
    LegalLedgerCheckRequest,
    LegalLedgerCheckResponse,
    HighAgeBenefitRequest,
    HighAgeBenefitResponse,
    InjuryAllowanceRequest,
    MaternityAllowanceRequest,
    HealthInsuranceBenefitResponse,
    ShortTimeInsuranceRequest,
    ShortTimeInsuranceResponse,
    ChildcareLeaveBenefitRequest,
    ChildcareLeaveBenefitResponse,
    CaregiverLeaveBenefitRequest,
    CaregiverLeaveBenefitResponse,
    LaborInsuranceInstallmentResponse,
    SanteiExportRequest,
    QualificationAcquisitionExportRequest,
    ResidenceTaxResponse,
    SocialInsurancePremiumResponse,
)
from app.services.auto_journal import generate_payroll_journal
from app.services.labor_insurance import (
    BUSINESS_TYPE_GENERAL,
    DEFAULT_WORKERS_COMPENSATION_RATE,
    LaborInsuranceService,
)
from app.services.labor_insurance_annual import LaborInsuranceAnnualUpdateService
from app.services.bonus_employment_insurance import BonusEmploymentInsuranceService
from app.services.bonus_withholding_tax import BonusWithholdingTaxService
from app.services.bonus_net_pay import BonusNetPayService
from app.services.labor_insurance_installment import LaborInsuranceInstallmentService
from app.services.overtime_pay import OvertimePayService
from app.services.santei_export import SanteiEmployee, SanteiKisoService, SanteiMonth
from app.services.notification_service import create_notification
from app.services.standard_remuneration import RemunerationMonth
from app.services.standard_bonus import BonusEmployee, StandardBonusService
from app.services.qualification_acquisition import AcquisitionEmployee, QualificationAcquisitionService
from app.services.social_insurance import (
    DEFAULT_CARE_INSURANCE_RATE,
    DEFAULT_HEALTH_INSURANCE_RATE,
    SocialInsurancePremiumService,
)
from app.services.monthly_revision import MonthlyRevisionService, RevisionEmployee
from app.services.residence_tax import ResidenceTaxSpecialCollectionService
from app.services.commute_allowance import CommuteAllowanceService, MODE_TRANSIT
from app.services.paid_leave import PaidLeaveService
from app.services.overtime_limit import MonthlyOvertime, OvertimeLimitService
from app.services.retirement_income_tax import RetirementIncomeTaxService
from app.services.monthly_payslip import MonthlyPayslipService
from app.services.minimum_wage import MinimumWageService, WAGE_TYPE_HOURLY
from app.services.dependent_eligibility import DependentEligibilityService
from app.services.social_insurance_exemption import LEAVE_CHILDCARE, SocialInsuranceExemptionService, TARGET_MONTHLY
from app.services.year_end_adjustment import YearEndAdjustmentService
from app.services.legal_ledger import LegalLedgerService
from app.services.high_age_benefit import HighAgeEmploymentBenefitService
from app.services.health_insurance_benefit import HealthInsuranceBenefitService
from app.services.short_time_insurance import ShortTimeWorkerInsuranceService
from app.services.childcare_leave_benefit import ChildcareLeaveBenefitService
from app.services.caregiver_leave_benefit import CaregiverLeaveBenefitService

router = APIRouter()


@router.post("/short-time-insurance/judge")
async def judge_short_time_insurance(
    payload: ShortTimeInsuranceRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> ShortTimeInsuranceResponse:
    try:
        result = ShortTimeWorkerInsuranceService.judge(
            weekly_hours=payload.weekly_hours,
            monthly_wage=payload.monthly_wage,
            employment_over_2_months=payload.employment_over_2_months,
            is_student=payload.is_student,
            company_insured_count=payload.company_insured_count,
            labor_agreement=payload.labor_agreement,
            meets_three_quarters_standard=payload.meets_three_quarters_standard,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ShortTimeInsuranceResponse.model_validate(result)


@router.post("/childcare-leave-benefit/calculate")
async def calculate_childcare_leave_benefit(
    payload: ChildcareLeaveBenefitRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> ChildcareLeaveBenefitResponse:
    try:
        result = ChildcareLeaveBenefitService.compute(
            wage_total_6m=payload.wage_total_6m,
            insured_months=payload.insured_months,
            payment_days=payload.payment_days,
            cumulative_days_before=payload.cumulative_days_before,
            wage_paid_during_leave=payload.wage_paid_during_leave,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ChildcareLeaveBenefitResponse.model_validate(result)


@router.post("/caregiver-leave-benefit/calculate")
async def calculate_caregiver_leave_benefit(
    payload: CaregiverLeaveBenefitRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> CaregiverLeaveBenefitResponse:
    try:
        result = CaregiverLeaveBenefitService.compute(
            wage_total_6m=payload.wage_total_6m,
            insured_months=payload.insured_months,
            payment_days=payload.payment_days,
            cumulative_days_before=payload.cumulative_days_before,
            wage_paid_during_leave=payload.wage_paid_during_leave,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CaregiverLeaveBenefitResponse.model_validate(result)


@router.post("/injury-allowance/calculate")
async def calculate_injury_allowance(
    payload: InjuryAllowanceRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> HealthInsuranceBenefitResponse:
    try:
        result = HealthInsuranceBenefitService.injury_allowance(
            avg_standard_monthly=payload.avg_standard_monthly,
            insured_months=payload.insured_months,
            absent_days=payload.absent_days,
            waiting_completed=payload.waiting_completed,
            daily_remuneration=payload.daily_remuneration,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return HealthInsuranceBenefitResponse.model_validate(result)


@router.post("/maternity-allowance/calculate")
async def calculate_maternity_allowance(
    payload: MaternityAllowanceRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> HealthInsuranceBenefitResponse:
    try:
        result = HealthInsuranceBenefitService.maternity_allowance(
            avg_standard_monthly=payload.avg_standard_monthly,
            insured_months=payload.insured_months,
            days_before_birth=payload.days_before_birth,
            days_after_birth=payload.days_after_birth,
            multiple_pregnancy=payload.multiple_pregnancy,
            daily_remuneration=payload.daily_remuneration,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return HealthInsuranceBenefitResponse.model_validate(result)


@router.post("/high-age-benefit/calculate")
async def calculate_high_age_benefit(
    payload: HighAgeBenefitRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> HighAgeBenefitResponse:
    try:
        result = HighAgeEmploymentBenefitService.compute(
            age=payload.age,
            insured_months=payload.insured_months,
            wage_at_60=payload.wage_at_60,
            current_wage=payload.current_wage,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return HighAgeBenefitResponse.model_validate(result)


@router.post("/legal-ledger/check")
async def check_legal_ledger(
    payload: LegalLedgerCheckRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> LegalLedgerCheckResponse:
    try:
        result = LegalLedgerService.check(
            ledger_type=payload.ledger_type,
            present_fields=payload.present_fields,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LegalLedgerCheckResponse.model_validate(result)


@router.get("/year-end-adjustment")
async def calculate_year_end_adjustment(
    annual_gross_salary: Decimal = Query(..., description="年間給与収入"),  # noqa: B008
    total_income_deductions: Decimal = Query(..., description="所得控除合計(社保・配偶者・扶養・基礎等)"),  # noqa: B008
    withheld_tax_total: Decimal = Query(..., description="徴収済みの源泉徴収税額合計"),  # noqa: B008
    housing_loan_credit: Decimal = Query(Decimal("0"), description="住宅借入金等特別控除(税額控除)"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> YearEndAdjustmentCalcResponse:
    try:
        result = YearEndAdjustmentService.compute(
            annual_gross_salary=annual_gross_salary,
            total_income_deductions=total_income_deductions,
            withheld_tax_total=withheld_tax_total,
            housing_loan_credit=housing_loan_credit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return YearEndAdjustmentCalcResponse.model_validate(result)


@router.get("/social-insurance/leave-exemption")
async def check_social_insurance_leave_exemption(
    leave_type: str = Query(LEAVE_CHILDCARE, description="休業区分: maternity(産前産後) / childcare(育児)"),  # noqa: B008
    target: str = Query(TARGET_MONTHLY, description="対象: monthly(月次) / bonus(賞与)"),  # noqa: B008
    month_last_day_on_leave: bool = Query(False, description="その月の末日が休業期間中か"),  # noqa: B008
    days_on_leave_in_month: int = Query(0, description="当月の育児休業日数(月次14日ルール)"),  # noqa: B008
    continuous_leave_over_one_month: bool = Query(False, description="賞与月末を含む連続1か月超の育休か"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> SocialInsuranceExemptionResponse:
    try:
        result = SocialInsuranceExemptionService.check(
            leave_type=leave_type,
            target=target,
            month_last_day_on_leave=month_last_day_on_leave,
            days_on_leave_in_month=days_on_leave_in_month,
            continuous_leave_over_one_month=continuous_leave_over_one_month,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SocialInsuranceExemptionResponse.model_validate(result)


@router.get("/dependent-eligibility/check")
async def check_dependent_eligibility(
    annual_income: Decimal = Query(..., description="被扶養者の年間収入見込み"),  # noqa: B008
    is_senior_or_disabled: bool = Query(False, description="60歳以上または障害者"),  # noqa: B008
    cohabiting: bool = Query(True, description="被保険者と同一世帯か"),  # noqa: B008
    insured_annual_income: Decimal | None = Query(None, description="被保険者の年間収入(同居時)"),  # noqa: B008
    remittance_amount: Decimal | None = Query(None, description="被保険者からの仕送り額(別居時)"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> DependentEligibilityResponse:
    try:
        result = DependentEligibilityService.check(
            annual_income=annual_income,
            is_senior_or_disabled=is_senior_or_disabled,
            cohabiting=cohabiting,
            insured_annual_income=insured_annual_income,
            remittance_amount=remittance_amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DependentEligibilityResponse.model_validate(result)


@router.get("/minimum-wage/check")
async def check_minimum_wage(
    minimum_hourly_wage: Decimal = Query(..., description="地域別最低賃金額(時間額)"),  # noqa: B008
    wage_type: str = Query(WAGE_TYPE_HOURLY, description="賃金形態: hourly / monthly"),  # noqa: B008
    hourly_wage: Decimal | None = Query(None, description="時給(hourly時)"),  # noqa: B008
    monthly_wage: Decimal | None = Query(None, description="最低賃金対象の月額賃金(monthly時)"),  # noqa: B008
    monthly_scheduled_hours: Decimal | None = Query(None, description="月平均所定労働時間(monthly時)"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> MinimumWageCheckResponse:
    try:
        result = MinimumWageService.check(
            minimum_hourly_wage=minimum_hourly_wage,
            wage_type=wage_type,
            hourly_wage=hourly_wage,
            monthly_wage=monthly_wage,
            monthly_scheduled_hours=monthly_scheduled_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MinimumWageCheckResponse.model_validate(result)


@router.get("/monthly-payslip")
async def calculate_monthly_payslip(
    base_salary: Decimal = Query(..., description="基本給"),  # noqa: B008
    standard_monthly_remuneration: Decimal = Query(..., description="標準報酬月額(社保計算の基礎)"),  # noqa: B008
    overtime_pay: Decimal = Query(Decimal("0"), description="割増賃金"),  # noqa: B008
    other_taxable_allowances: Decimal = Query(Decimal("0"), description="課税手当合計"),  # noqa: B008
    non_taxable_commute_allowance: Decimal = Query(Decimal("0"), description="非課税通勤手当"),  # noqa: B008
    income_tax: Decimal = Query(Decimal("0"), description="源泉所得税(月額表 甲欄)"),  # noqa: B008
    residence_tax: Decimal = Query(Decimal("0"), description="住民税(特別徴収額)"),  # noqa: B008
    other_deductions: Decimal = Query(Decimal("0"), description="その他控除"),  # noqa: B008
    business_type: str = Query(BUSINESS_TYPE_GENERAL, description="事業区分(雇用保険料率)"),  # noqa: B008
    health_rate: Decimal = Query(DEFAULT_HEALTH_INSURANCE_RATE, description="健康保険料率"),  # noqa: B008
    care_rate: Decimal = Query(DEFAULT_CARE_INSURANCE_RATE, description="介護保険料率"),  # noqa: B008
    care_applicable: bool = Query(False, description="40〜64歳の介護保険適用有無"),  # noqa: B008
    employment_insurance_exempt: bool = Query(False, description="雇用保険料免除(65歳以上等)"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> MonthlyPayslipResponse:
    try:
        result = MonthlyPayslipService.compute(
            base_salary=base_salary,
            standard_monthly_remuneration=standard_monthly_remuneration,
            overtime_pay=overtime_pay,
            other_taxable_allowances=other_taxable_allowances,
            non_taxable_commute_allowance=non_taxable_commute_allowance,
            income_tax=income_tax,
            residence_tax=residence_tax,
            other_deductions=other_deductions,
            business_type=business_type,
            health_rate=health_rate,
            care_rate=care_rate,
            care_applicable=care_applicable,
            employment_insurance_exempt=employment_insurance_exempt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MonthlyPayslipResponse.model_validate(result)


@router.get("/retirement-income-tax")
async def calculate_retirement_income_tax(
    severance_pay: Decimal = Query(..., description="退職手当等の額"),  # noqa: B008
    months_of_service: int = Query(..., description="勤続月数(1年未満切上)"),  # noqa: B008
    is_specified_officer_5yr_or_less: bool = Query(False, description="特定役員退職手当等(役員等・勤続5年以下)"),  # noqa: B008
    is_short_term_5yr_or_less: bool = Query(False, description="短期退職手当等(役員等以外・勤続5年以下)"),  # noqa: B008
    statement_submitted: bool = Query(True, description="退職所得の受給に関する申告書の提出有無"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> RetirementIncomeTaxResponse:
    try:
        result = RetirementIncomeTaxService.compute(
            severance_pay=severance_pay,
            months_of_service=months_of_service,
            is_specified_officer_5yr_or_less=is_specified_officer_5yr_or_less,
            is_short_term_5yr_or_less=is_short_term_5yr_or_less,
            statement_submitted=statement_submitted,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RetirementIncomeTaxResponse.model_validate(result)


@router.post("/overtime-limit/check")
async def check_overtime_limit(
    payload: OvertimeLimitCheckRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> OvertimeLimitCheckResponse:
    try:
        result = OvertimeLimitService.check(
            [
                MonthlyOvertime(overtime_hours=m.overtime_hours, holiday_work_hours=m.holiday_work_hours)
                for m in payload.months
            ]
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OvertimeLimitCheckResponse.model_validate(result)


@router.get("/paid-leave/grant")
async def calculate_paid_leave_grant(
    months_of_service: int = Query(..., description="継続勤務月数"),  # noqa: B008
    weekly_working_days: int = Query(5, description="週所定労働日数"),  # noqa: B008
    weekly_working_hours: Decimal = Query(Decimal("40"), description="週所定労働時間"),  # noqa: B008
    attendance_rate: Decimal = Query(Decimal("1"), description="全労働日に対する出勤率(0〜1)"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> PaidLeaveGrantResponse:
    try:
        result = PaidLeaveService.grant_days(
            months_of_service=months_of_service,
            weekly_working_days=weekly_working_days,
            weekly_working_hours=weekly_working_hours,
            attendance_rate=attendance_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PaidLeaveGrantResponse.model_validate(result)


@router.get("/commute-allowance/non-taxable")
async def calculate_commute_allowance_non_taxable(
    mode: str = Query(MODE_TRANSIT, description="通勤手段: transit(交通機関) / car(マイカー等)"),  # noqa: B008
    monthly_allowance: Decimal = Query(..., description="1か月の通勤手当支給額"),  # noqa: B008
    one_way_distance_km: Decimal | None = Query(None, description="片道通勤距離(km), car時に必須"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> CommuteAllowanceResponse:
    try:
        result = CommuteAllowanceService.compute(
            mode=mode,
            monthly_allowance=monthly_allowance,
            one_way_distance_km=one_way_distance_km,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CommuteAllowanceResponse.model_validate(result)


@router.get("/residence-tax/special-collection")
async def calculate_residence_tax_special_collection(
    annual_tax: Decimal = Query(..., description="市町村から通知された年税額"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> ResidenceTaxResponse:
    try:
        result = ResidenceTaxSpecialCollectionService.compute(annual_tax=annual_tax)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ResidenceTaxResponse.model_validate(result)


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




def _gross_for_labor_insurance(emp: Employee, payroll_record: PayrollRecord | None) -> Decimal:
    if payroll_record is not None:
        return Decimal(payroll_record.total_gross)
    return Decimal(emp.base_salary)


# --- Employee endpoints ---

@router.get("/employees", response_model=EmployeeListResponse)
async def list_employees(
    company_id: UUID = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> EmployeeListResponse:
    count_result = await db.execute(
        select(func.count()).select_from(Employee).where(
            Employee.company_id == company_id,
            Employee.is_deleted == False,  # noqa: E712
        )
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(Employee).where(
            Employee.company_id == company_id,
            Employee.is_deleted == False,  # noqa: E712
        ).order_by(Employee.employee_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    employees = result.scalars().all()
    items = [_to_employee_response(e) for e in employees]
    return EmployeeListResponse(items=items, total=total, page=page, page_size=page_size)


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




@router.get("/social-insurance-premium")
async def calculate_social_insurance_premium(
    standard_monthly_remuneration: Decimal = Query(..., description="標準報酬月額"),  # noqa: B008
    health_rate: Decimal = Query(Decimal("0.0998"), description="健康保険料率"),  # noqa: B008
    care_rate: Decimal = Query(Decimal("0.016"), description="介護保険料率"),  # noqa: B008
    care_applicable: bool = Query(False, description="40〜64歳の介護保険適用有無"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> SocialInsurancePremiumResponse:
    try:
        result = SocialInsurancePremiumService.compute(
            standard_monthly_remuneration=standard_monthly_remuneration,
            health_rate=health_rate,
            care_rate=care_rate,
            care_applicable=care_applicable,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SocialInsurancePremiumResponse.model_validate(result)


@router.get("/bonus-employment-insurance")
async def calculate_bonus_employment_insurance(
    bonus_amount: Decimal = Query(..., description="賞与額"),  # noqa: B008
    business_type: str = Query(BUSINESS_TYPE_GENERAL, description="事業区分"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> BonusEmploymentInsuranceResponse:
    try:
        result = BonusEmploymentInsuranceService.compute(
            bonus_amount=bonus_amount,
            business_type=business_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BonusEmploymentInsuranceResponse.model_validate(result)


@router.get("/bonus-net-pay")
async def calculate_bonus_net_pay(
    gross_bonus: Decimal = Query(..., description="賞与額"),  # noqa: B008
    business_type: str = Query(BUSINESS_TYPE_GENERAL, description="事業区分"),  # noqa: B008
    health_rate: Decimal = Query(DEFAULT_HEALTH_INSURANCE_RATE, description="健康保険料率"),  # noqa: B008
    care_rate: Decimal = Query(DEFAULT_CARE_INSURANCE_RATE, description="介護保険料率"),  # noqa: B008
    care_applicable: bool = Query(False, description="40〜64歳の介護保険適用有無"),  # noqa: B008
    bonus_tax_rate: Decimal = Query(..., description="賞与に対する源泉徴収税率"),  # noqa: B008
    prior_month_salary_after_social_insurance: Decimal | None = Query(None, description="前月給与(社会保険料等控除後)"),  # noqa: B008
    cumulative_health_standard_bonus_ytd: Decimal = Query(Decimal("0"), description="当年度の既支給累計標準賞与額"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> BonusNetPayResponse:
    try:
        result = BonusNetPayService.compute(
            gross_bonus=gross_bonus,
            business_type=business_type,
            health_rate=health_rate,
            care_rate=care_rate,
            care_applicable=care_applicable,
            bonus_tax_rate=bonus_tax_rate,
            prior_month_salary_after_social_insurance=prior_month_salary_after_social_insurance,
            cumulative_health_standard_bonus_ytd=cumulative_health_standard_bonus_ytd,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BonusNetPayResponse.model_validate(result)


@router.get("/bonus-withholding-tax")
async def calculate_bonus_withholding_tax(
    bonus_after_social_insurance: Decimal = Query(..., description="社会保険料等控除後の賞与額"),  # noqa: B008
    bonus_tax_rate: Decimal = Query(..., description="賞与に対する源泉徴収税率"),  # noqa: B008
    prior_month_salary_after_social_insurance: Decimal | None = Query(None, description="前月給与(社会保険料等控除後)"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> BonusWithholdingTaxResponse:
    try:
        result = BonusWithholdingTaxService.compute(
            bonus_after_social_insurance=bonus_after_social_insurance,
            bonus_tax_rate=bonus_tax_rate,
            prior_month_salary_after_social_insurance=prior_month_salary_after_social_insurance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BonusWithholdingTaxResponse.model_validate(result)


@router.get("/bonus-social-insurance-premium")
async def calculate_bonus_social_insurance_premium(
    health_standard_bonus: Decimal = Query(..., description="健康保険用標準賞与額"),  # noqa: B008
    pension_standard_bonus: Decimal = Query(..., description="厚生年金保険用標準賞与額"),  # noqa: B008
    health_rate: Decimal = Query(Decimal("0.0998"), description="健康保険料率"),  # noqa: B008
    care_rate: Decimal = Query(Decimal("0.016"), description="介護保険料率"),  # noqa: B008
    care_applicable: bool = Query(False, description="40〜64歳の介護保険適用有無"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> SocialInsurancePremiumResponse:
    try:
        result = SocialInsurancePremiumService.compute_bonus(
            health_standard_bonus=health_standard_bonus,
            pension_standard_bonus=pension_standard_bonus,
            health_rate=health_rate,
            care_rate=care_rate,
            care_applicable=care_applicable,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SocialInsurancePremiumResponse.model_validate(result)


@router.get("/labor-insurance/installment")
async def calculate_labor_insurance_installment(
    estimated_premium: Decimal = Query(..., description="概算保険料額"),  # noqa: B008
    both_insurances: bool = Query(True, description="労災・雇用の両保険成立"),  # noqa: B008
    entrusted: bool = Query(False, description="労働保険事務組合への委託有無"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
) -> LaborInsuranceInstallmentResponse:
    try:
        result = LaborInsuranceInstallmentService.compute(
            estimated_premium=estimated_premium,
            both_insurances=both_insurances,
            entrusted=entrusted,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LaborInsuranceInstallmentResponse.model_validate(result)


@router.post("/monthly-revision/export")
async def export_monthly_revision(
    payload: MonthlyRevisionExportRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
) -> Response:
    try:
        employees = [
            RevisionEmployee(
                insured_number=employee.insured_number,
                name=employee.name,
                previous_health_standard=employee.previous_health_standard,
                previous_pension_standard=employee.previous_pension_standard,
                fixed_wage_changed=employee.fixed_wage_changed,
                months=[
                    RemunerationMonth(
                        payment_basis_days=month.payment_basis_days,
                        remuneration=month.remuneration,
                    )
                    for month in employee.months
                ],
            )
            for employee in payload.employees
        ]
        csv_content = MonthlyRevisionService.build_csv(employees)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="getsugaku_henkou.csv"'},
    )


@router.post("/bonus/export")
async def export_bonus(
    payload: BonusExportRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
) -> Response:
    try:
        employees = [
            BonusEmployee(
                insured_number=employee.insured_number,
                name=employee.name,
                payment_date=employee.payment_date,
                bonus_amount=employee.bonus_amount,
                fiscal_ytd_standard_bonus=employee.fiscal_ytd_standard_bonus,
                same_month_prior_standard_bonus=employee.same_month_prior_standard_bonus,
            )
            for employee in payload.employees
        ]
        csv_content = StandardBonusService.build_csv(employees)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bonus.csv"'},
    )


@router.post("/labor-insurance/annual-update/export")
async def export_labor_insurance_annual_update(
    payload: LaborInsuranceAnnualUpdateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
) -> Response:
    try:
        result = LaborInsuranceAnnualUpdateService.compute(
            prior_wage_total=payload.prior_wage_total,
            estimated_wage_total=payload.estimated_wage_total,
            business_type=payload.business_type,
            declared_prior_estimate=payload.declared_prior_estimate,
            workers_comp_rate=payload.workers_comp_rate,
        )
        csv_content = LaborInsuranceAnnualUpdateService.build_csv(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="rodo_hoken_nendo_koushin.csv"'},
    )


@router.get("/labor-insurance", response_model=LaborInsuranceSummaryResponse)
async def calculate_labor_insurance(
    company_id: UUID = Query(...),  # noqa: B008
    target_year: int = Query(...),  # noqa: B008
    target_month: int = Query(...),  # noqa: B008
    business_type: str = Query(...),  # noqa: B008
    workers_comp_rate: Decimal = Query(DEFAULT_WORKERS_COMPENSATION_RATE),  # noqa: B008
    senior_employee_ids: list[UUID] | None = Query(None),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> LaborInsuranceSummaryResponse:
    employees_result = await db.execute(
        select(Employee).where(
            Employee.company_id == company_id,
            Employee.is_active == True,  # noqa: E712
            Employee.is_deleted == False,  # noqa: E712
        ).order_by(Employee.employee_code)
    )
    employees = employees_result.scalars().all()

    payroll_result = await db.execute(
        select(PayrollRecord).where(
            PayrollRecord.company_id == company_id,
            PayrollRecord.payroll_year == target_year,
            PayrollRecord.payroll_month == target_month,
        )
    )
    payroll_records = {record.employee_id: record for record in payroll_result.scalars().all()}

    exempt_employee_ids = set(senior_employee_ids or [])

    items: list[LaborInsuranceEmployeeResponse] = []
    breakdowns = []
    for emp in employees:
        payroll_record = payroll_records.get(emp.employee_id)
        gross = _gross_for_labor_insurance(emp, payroll_record)
        is_exempt = emp.employee_id in exempt_employee_ids
        breakdown = LaborInsuranceService.calculate_employee_premium(
            gross_monthly_pay=gross,
            business_type=business_type,
            is_exempt=is_exempt,
            workers_comp_rate=workers_comp_rate,
        )
        breakdowns.append(breakdown)
        items.append(
            LaborInsuranceEmployeeResponse(
                employee_id=emp.employee_id,
                employee_name=emp.employee_name,
                gross_monthly_pay=gross,
                employment_insurance_employee=breakdown.employment_insurance_employee,
                employment_insurance_employer=breakdown.employment_insurance_employer,
                workers_comp_employer=breakdown.workers_comp_employer,
                total_employee=breakdown.total_employee,
                total_employer=breakdown.total_employer,
                total_premium=breakdown.total_premium,
            )
        )

    summary = LaborInsuranceService.summarize_company_premiums(breakdowns)
    return LaborInsuranceSummaryResponse(
        company_id=company_id,
        target_year=target_year,
        target_month=target_month,
        business_type=business_type,
        workers_comp_rate=workers_comp_rate,
        employee_count=summary.employee_count,
        total_employee_premium=summary.total_employee_premium,
        total_employer_premium=summary.total_employer_premium,
        total_premium=summary.total_premium,
        items=items,
    )

@router.get("/records", response_model=PayrollListResponse)
async def list_payroll_records(
    company_id: UUID = Query(...),
    payroll_year: int = Query(...),
    payroll_month: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> PayrollListResponse:
    """給与記録一覧を取得する（ページネーション対応）。"""
    base_query = (
        select(PayrollRecord, Employee.employee_name)
        .join(Employee, PayrollRecord.employee_id == Employee.employee_id)
        .where(
            PayrollRecord.company_id == company_id,
            PayrollRecord.payroll_year == payroll_year,
            PayrollRecord.payroll_month == payroll_month,
        )
    )

    # Count total
    count_query = (
        select(func.count())
        .select_from(PayrollRecord)
        .where(
            PayrollRecord.company_id == company_id,
            PayrollRecord.payroll_year == payroll_year,
            PayrollRecord.payroll_month == payroll_month,
        )
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginated query
    query = base_query.order_by(Employee.employee_code).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.all()
    items = [_to_payroll_response(rec, name) for rec, name in rows]

    return PayrollListResponse(items=items, total=total, page=page, page_size=page_size)


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


# --- Payroll approval workflow ---

VALID_PAYROLL_TRANSITIONS: dict[str, set[str]] = {
    "calculated": {"approved", "rejected"},
    "approved": {"paid"},
    "rejected": {"calculated"},
    "paid": set(),
}




@router.post("/qualification-acquisition/export")
async def export_qualification_acquisition(
    payload: QualificationAcquisitionExportRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
) -> Response:
    try:
        employees = [
            AcquisitionEmployee(
                insured_number=employee.insured_number,
                name=employee.name,
                birth_date=employee.birth_date,
                qualification_date=employee.qualification_date,
                estimated_monthly_remuneration=employee.estimated_monthly_remuneration,
            )
            for employee in payload.employees
        ]
        csv_content = QualificationAcquisitionService.build_csv(employees)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="shikaku_shutoku.csv"'},
    )


@router.post("/santei/export")
async def export_santei(
    payload: SanteiExportRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
) -> Response:
    try:
        employees = [
            SanteiEmployee(
                insured_number=employee.insured_number,
                name=employee.name,
                birth_date=employee.birth_date,
                previous_health_standard=employee.previous_health_standard,
                previous_pension_standard=employee.previous_pension_standard,
                applicable_year=employee.applicable_year,
                applicable_month=employee.applicable_month,
                months=[
                    SanteiMonth(
                        payment_basis_days=month.payment_basis_days,
                        currency_remuneration=month.currency_remuneration,
                        in_kind_remuneration=month.in_kind_remuneration,
                    )
                    for month in employee.months
                ],
            )
            for employee in payload.employees
        ]
        csv_content = SanteiKisoService.build_csv(employees)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="santei.csv"'},
    )

@router.post("/records/{payroll_id}/transition", response_model=PayrollRecordResponse)
async def transition_payroll_status(
    payroll_id: UUID,
    action: str = Query(..., description="approved, rejected, or paid"),
    company_id: UUID = Query(..., description="会社ID（テナント検証用）"),
    current_user: CurrentUser = Depends(require_permission(Permission.PAYROLL_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> PayrollRecordResponse:
    """給与レコードのステータスを遷移させる。"""
    valid_actions = {"approved", "rejected", "paid"}
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"無効なアクション: {action}")

    result = await db.execute(
        select(PayrollRecord, Employee.employee_name)
        .join(Employee, PayrollRecord.employee_id == Employee.employee_id)
        .where(PayrollRecord.payroll_id == payroll_id, PayrollRecord.company_id == company_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="給与レコードが見つかりません")

    rec, emp_name = row
    current_status = rec.status
    allowed = VALID_PAYROLL_TRANSITIONS.get(current_status, set())
    if action not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"ステータス「{current_status}」から「{action}」への遷移は許可されていません",
        )

    if action == "paid":
        rec.status = "paid"
    elif action == "approved":
        rec.status = "approved"
    elif action == "rejected":
        rec.status = "rejected"

    await db.commit()
    await db.refresh(rec)
    return _to_payroll_response(rec, emp_name)


@router.post("/records/batch-transition", response_model=list[PayrollRecordResponse])
async def batch_transition_payroll(
    company_id: UUID = Query(...),
    payroll_year: int = Query(...),
    payroll_month: int = Query(...),
    action: str = Query(..., description="approved, rejected, or paid"),
    current_user: CurrentUser = Depends(require_permission(Permission.PAYROLL_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> list[PayrollRecordResponse]:
    """指定月の全給与レコードのステータスを一括遷移させる。"""
    valid_actions = {"approved", "rejected", "paid"}
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"無効なアクション: {action}")

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
    if not rows:
        raise HTTPException(status_code=404, detail="該当月の給与レコードがありません")

    allowed = VALID_PAYROLL_TRANSITIONS.get(rows[0][0].status, set())
    if action not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"現在のステータス「{rows[0][0].status}」から「{action}」への遷移は許可されていません",
        )

    updated: list[PayrollRecordResponse] = []
    total_gross_sum = Decimal("0")
    total_deductions_sum = Decimal("0")
    net_pay_sum = Decimal("0")
    for rec, emp_name in rows:
        rec.status = action
        total_gross_sum += rec.total_gross
        total_deductions_sum += rec.total_deductions
        net_pay_sum += rec.net_pay
        updated.append(_to_payroll_response(rec, emp_name))

    # Auto-generate payroll journal on batch "paid" transition
    if action == "paid":
        with suppress(ValueError):
            await generate_payroll_journal(
                db,
                company_id=company_id,
                payroll_year=payroll_year,
                payroll_month=payroll_month,
                total_gross=total_gross_sum,
                total_deductions=total_deductions_sum,
                net_pay=net_pay_sum,
                created_by=current_user.user_id,
            )

    # Notify on batch transition
    action_labels = {"approved": "承認", "rejected": "差戻し", "paid": "支払完了"}
    with suppress(Exception):
        await create_notification(db, current_user.tenant_id, NotificationCreate(
            company_id=company_id,
            category="payroll",
            priority="high" if action == "paid" else "normal",
            title=f"給与 {payroll_year}年{payroll_month}月 一括{action_labels[action]}",
            body=f"{len(updated)}件の給与レコードを{action_labels[action]}しました。",
            action_url="/payroll",
        ))

    await db.commit()
    return updated

@router.get("/overtime-premium")
async def calculate_overtime_premium(
    hourly_wage: Decimal = Query(..., description="時給"),  # noqa: B008
    overtime_hours: Decimal = Query(Decimal("0"), description="法定時間外(月60時間以内)"),  # noqa: B008
    overtime_over_60_hours: Decimal = Query(Decimal("0"), description="法定時間外(月60時間超)"),  # noqa: B008
    late_night_hours: Decimal = Query(Decimal("0"), description="深夜時間"),  # noqa: B008
    holiday_hours: Decimal = Query(Decimal("0"), description="法定休日時間"),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, Decimal]:
    try:
        result = OvertimePayService.compute(
            hourly_wage=hourly_wage,
            overtime_hours=overtime_hours,
            overtime_over_60_hours=overtime_over_60_hours,
            late_night_hours=late_night_hours,
            holiday_hours=holiday_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "hourly_wage": hourly_wage,
        "overtime_pay": result.overtime_pay,
        "overtime_over_60_pay": result.overtime_over_60_pay,
        "late_night_pay": result.late_night_pay,
        "holiday_pay": result.holiday_pay,
        "total_premium": result.total_premium,
    }
