"""月次給与クローズのオーケストレーション。

個別の取込API(算定基礎届・月額変更届・賞与支払届・労働保険料・割増賃金)は揃っていても、
「今月どの届出が必要か」を人間が判断して複数APIを個別に叩く工程が残る。この判断は法定の
提出時期で決まるため機械化でき、工程自体を削除できる。本サービスは対象年月と手元のCSVから

    1. 提出時期に基づく必要な届出の自動選定 (7月=算定基礎届・6月=労働保険年度更新・毎月=割増賃金)
    2. 事象ベースの届出は入力があるときだけ実行 (賞与支払届・月額変更届)
    3. 必要なのに入力が無い/失敗した届出を `blocking_forms` として提示

を1回で処理する。**1つの届出の失敗が他を止めない**のが要点で、取込エラーはその届出の
`status="failed"` に閉じ込め、残りは処理を続ける(月末に1件の列名ミスで全処理が落ちると
締めが止まるため)。各届出の算定は既存の取込サービスへ委譲し、本サービスは選定と集約のみ。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.services.attendance_import import AttendanceImportService
from app.services.bonus_import import BonusImportService
from app.services.labor_insurance import BUSINESS_TYPE_GENERAL
from app.services.payroll_wage_import import PayrollWageImportService
from app.services.revision_import import RevisionImportService
from app.services.santei_import import SanteiImportService

FORM_ATTENDANCE = "attendance_overtime"
FORM_SANTEI = "santei"
FORM_LABOR_INSURANCE = "labor_insurance_annual_update"
FORM_MONTHLY_REVISION = "monthly_revision"
FORM_BONUS = "bonus"

STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_MISSING_INPUT = "missing_input"
STATUS_NOT_REQUIRED = "not_required"

FORM_LABELS: dict[str, str] = {
    FORM_ATTENDANCE: "割増賃金",
    FORM_SANTEI: "算定基礎届",
    FORM_LABOR_INSURANCE: "労働保険 年度更新",
    FORM_MONTHLY_REVISION: "月額変更届",
    FORM_BONUS: "賞与支払届",
}

# 提出時期が暦で決まる届出の対象月(それ以外は事象ベース)
REQUIRED_MONTHS: dict[str, tuple[int, ...]] = {
    FORM_ATTENDANCE: tuple(range(1, 13)),
    FORM_SANTEI: (7,),
    FORM_LABOR_INSURANCE: (6,),
}

FORM_ORDER: tuple[str, ...] = (
    FORM_ATTENDANCE,
    FORM_SANTEI,
    FORM_LABOR_INSURANCE,
    FORM_MONTHLY_REVISION,
    FORM_BONUS,
)


@dataclass(frozen=True)
class PayrollCloseInput:
    fiscal_year: int
    target_month: int
    business_type: str = BUSINESS_TYPE_GENERAL
    attendance_csv: str | None = None
    santei_csv: str | None = None
    labor_insurance_csv: str | None = None
    revision_csv: str | None = None
    bonus_csv: str | None = None
    column_maps: dict[str, dict[str, str]] | None = None


@dataclass(frozen=True)
class FormOutcome:
    form: str
    label: str
    status: str
    required: bool
    detail: str
    statutory_deadline: date | None
    summary: dict[str, str]
    csv_text: str | None


@dataclass(frozen=True)
class PayrollCloseResult:
    fiscal_year: int
    target_month: int
    outcomes: list[FormOutcome]
    completed_forms: list[str]
    failed_forms: list[str]
    blocking_forms: list[str]
    close_ready: bool


class PayrollCloseService:
    """月次クローズで必要な届出を自動選定し一括処理する純粋サービス。"""

    @staticmethod
    def statutory_deadline(form: str, fiscal_year: int) -> date | None:
        if form == FORM_SANTEI:
            return date(fiscal_year, 7, 10)
        if form == FORM_LABOR_INSURANCE:
            return date(fiscal_year, 7, 10)
        return None

    @staticmethod
    def is_required(form: str, target_month: int) -> bool:
        return target_month in REQUIRED_MONTHS.get(form, ())

    @classmethod
    def _column_map(cls, payload: PayrollCloseInput, form: str) -> dict[str, str] | None:
        return (payload.column_maps or {}).get(form)

    @classmethod
    def _run_attendance(cls, csv_text: str, payload: PayrollCloseInput) -> tuple[dict[str, str], None]:
        records = AttendanceImportService.parse_csv(csv_text, cls._column_map(payload, FORM_ATTENDANCE))
        result = AttendanceImportService.compute(records)
        return (
            {
                "employee_count": str(result.employee_count),
                "total_premium": str(result.total_premium),
                "exceeding_45_hours_count": str(len(result.exceeding_employee_ids)),
            },
            None,
        )

    @classmethod
    def _run_santei(cls, csv_text: str, payload: PayrollCloseInput) -> tuple[dict[str, str], str]:
        rows = SanteiImportService.parse_csv(csv_text, cls._column_map(payload, FORM_SANTEI))
        result = SanteiImportService.compute(rows, applicable_year=payload.fiscal_year)
        return (
            {
                "employee_count": str(result.employee_count),
                "manual_review_count": str(len(result.manual_review_numbers)),
            },
            result.csv_text,
        )

    @classmethod
    def _run_labor_insurance(
        cls, csv_text: str, payload: PayrollCloseInput
    ) -> tuple[dict[str, str], None]:
        records = PayrollWageImportService.parse_csv(
            csv_text, cls._column_map(payload, FORM_LABOR_INSURANCE)
        )
        result = PayrollWageImportService.compute(records, business_type=payload.business_type)
        return (
            {
                "employee_count": str(result.employee_count),
                "workers_comp_premium": str(result.workers_comp_premium),
                "employment_premium": str(result.employment_premium),
                "determined_premium": str(result.determined_premium),
            },
            None,
        )

    @classmethod
    def _run_revision(cls, csv_text: str, payload: PayrollCloseInput) -> tuple[dict[str, str], str]:
        rows = RevisionImportService.parse_csv(
            csv_text, cls._column_map(payload, FORM_MONTHLY_REVISION)
        )
        result = RevisionImportService.compute(rows, start_year=payload.fiscal_year)
        return (
            {
                "employee_count": str(result.employee_count),
                "revision_required_count": str(len(result.revision_required_numbers)),
            },
            result.csv_text,
        )

    @classmethod
    def _run_bonus(cls, csv_text: str, payload: PayrollCloseInput) -> tuple[dict[str, str], str]:
        rows = BonusImportService.parse_csv(csv_text, cls._column_map(payload, FORM_BONUS))
        result = BonusImportService.compute(rows, fiscal_year=payload.fiscal_year)
        return (
            {
                "payment_count": str(result.payment_count),
                "employee_count": str(result.employee_count),
                "total_health_standard_bonus": str(result.total_health_standard_bonus),
                "total_pension_standard_bonus": str(result.total_pension_standard_bonus),
            },
            result.csv_text,
        )

    @classmethod
    def _csv_for(cls, payload: PayrollCloseInput, form: str) -> str | None:
        sources: dict[str, str | None] = {
            FORM_ATTENDANCE: payload.attendance_csv,
            FORM_SANTEI: payload.santei_csv,
            FORM_LABOR_INSURANCE: payload.labor_insurance_csv,
            FORM_MONTHLY_REVISION: payload.revision_csv,
            FORM_BONUS: payload.bonus_csv,
        }
        csv_text = sources[form]
        if csv_text is None or csv_text.strip() == "":
            return None
        return csv_text

    @classmethod
    def _execute(
        cls, form: str, csv_text: str, payload: PayrollCloseInput
    ) -> tuple[dict[str, str], str | None]:
        if form == FORM_ATTENDANCE:
            return cls._run_attendance(csv_text, payload)
        if form == FORM_SANTEI:
            return cls._run_santei(csv_text, payload)
        if form == FORM_LABOR_INSURANCE:
            return cls._run_labor_insurance(csv_text, payload)
        if form == FORM_MONTHLY_REVISION:
            return cls._run_revision(csv_text, payload)
        return cls._run_bonus(csv_text, payload)

    @classmethod
    def run(cls, payload: PayrollCloseInput) -> PayrollCloseResult:
        if not 1 <= payload.target_month <= 12:
            raise ValueError("target_month must be between 1 and 12")
        if all(cls._csv_for(payload, form) is None for form in FORM_ORDER):
            raise ValueError("at least one csv input is required")

        outcomes: list[FormOutcome] = []
        completed: list[str] = []
        failed: list[str] = []
        blocking: list[str] = []

        for form in FORM_ORDER:
            required = cls.is_required(form, payload.target_month)
            deadline = cls.statutory_deadline(form, payload.fiscal_year)
            csv_text = cls._csv_for(payload, form)

            if csv_text is None:
                status = STATUS_MISSING_INPUT if required else STATUS_NOT_REQUIRED
                detail = (
                    f"{FORM_LABELS[form]}は{payload.target_month}月の処理対象だが入力CSVが無い"
                    if required
                    else f"{FORM_LABELS[form]}は{payload.target_month}月の処理対象外"
                )
                if required:
                    blocking.append(form)
                outcomes.append(
                    FormOutcome(
                        form=form,
                        label=FORM_LABELS[form],
                        status=status,
                        required=required,
                        detail=detail,
                        statutory_deadline=deadline,
                        summary={},
                        csv_text=None,
                    )
                )
                continue

            try:
                summary, generated_csv = cls._execute(form, csv_text, payload)
            except (ValueError, ArithmeticError, KeyError) as exc:
                failed.append(form)
                if required:
                    blocking.append(form)
                outcomes.append(
                    FormOutcome(
                        form=form,
                        label=FORM_LABELS[form],
                        status=STATUS_FAILED,
                        required=required,
                        detail=str(exc),
                        statutory_deadline=deadline,
                        summary={},
                        csv_text=None,
                    )
                )
                continue

            completed.append(form)
            outcomes.append(
                FormOutcome(
                    form=form,
                    label=FORM_LABELS[form],
                    status=STATUS_COMPLETED,
                    required=required,
                    detail=f"{FORM_LABELS[form]}を処理した",
                    statutory_deadline=deadline,
                    summary=summary,
                    csv_text=generated_csv,
                )
            )

        return PayrollCloseResult(
            fiscal_year=payload.fiscal_year,
            target_month=payload.target_month,
            outcomes=outcomes,
            completed_forms=completed,
            failed_forms=failed,
            blocking_forms=blocking,
            close_ready=not blocking,
        )
