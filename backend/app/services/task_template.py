"""月次/日次業務エンジンの定型タスク生成（純粋ロジック）。

DBやI/Oに依存せず、対象期間から生成すべき事務タスク仕様（task_type / title /
due_date）を決定論的に算出する。月初・月中・月末テンプレートと毎日の定型業務を
カタログとして保持し、エンドポイント側がこれを office_tasks へ実体化する。
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

MONTHLY_PHASE_OPENING = "opening"
MONTHLY_PHASE_MIDDLE = "middle"
MONTHLY_PHASE_CLOSING = "closing"

# 月末を表すセンチネル（実際の締日はその月の末日に丸める）。
_LAST_DAY = -1


@dataclass(frozen=True)
class TaskSpec:
    """生成された事務タスク1件の仕様。"""

    task_type: str
    title: str
    due_date: date


@dataclass(frozen=True)
class _MonthlyTemplate:
    phase: str
    task_type: str
    title: str
    due_day: int


@dataclass(frozen=True)
class _AnnualTemplate:
    task_type: str
    title: str
    month: int
    day: int


# 年次業務テンプレート（暦年で期日が固定の法定イベント）。
# 法的根拠を併記。法人税・消費税の確定申告は会計期間依存のため別途算出する。
ANNUAL_FIXED_TEMPLATES: tuple[_AnnualTemplate, ...] = (
    # 法定調書合計表・給与支払報告書（所得税法226条等、提出期限 翌年1/31）
    _AnnualTemplate("legal_records_submission", "法定調書・給与支払報告書提出", 1, 31),
    # 償却資産申告（地方税法383条、申告期限 1/31）
    _AnnualTemplate("depreciable_asset_return", "償却資産申告", 1, 31),
    # 労働保険 年度更新（労働保険徴収法、6/1〜7/10）
    _AnnualTemplate("labor_insurance_renewal", "労働保険 年度更新", 7, 10),
    # 社会保険 算定基礎届（健保法・厚年法、7/1〜7/10）
    _AnnualTemplate("social_insurance_calc_base", "社会保険 算定基礎届", 7, 10),
    # 年末調整（所得税法190条 WT-020、12月給与支給時）
    _AnnualTemplate("year_end_adjustment", "年末調整", 12, 31),
)


# 月次業務テンプレート（月初/月中/月末）。due_day はその月内の締日。
MONTHLY_TEMPLATES: tuple[_MonthlyTemplate, ...] = (
    _MonthlyTemplate(MONTHLY_PHASE_OPENING, "source_document_collection", "証憑回収・取込", 5),
    _MonthlyTemplate(MONTHLY_PHASE_OPENING, "payroll_preparation", "給与計算準備", 10),
    _MonthlyTemplate(MONTHLY_PHASE_MIDDLE, "interim_payment_check", "中間支払確認", 15),
    _MonthlyTemplate(MONTHLY_PHASE_MIDDLE, "invoice_issue", "請求書発行", 25),
    _MonthlyTemplate(MONTHLY_PHASE_CLOSING, "monthly_close", "月次決算", _LAST_DAY),
    _MonthlyTemplate(MONTHLY_PHASE_CLOSING, "bank_reconciliation", "月末銀行消込", _LAST_DAY),
)

# 日次業務テンプレート（毎朝の自動実行：データ取得→AI処理→確認→通知）。
DAILY_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("bank_data_fetch", "口座明細取得"),
    ("ocr_processing", "証憑OCR処理"),
    ("journal_review", "自動仕訳の確認"),
    ("daily_notification", "日次サマリ通知"),
)


class TaskTemplateService:
    """対象期間から事務タスク仕様を生成する純粋サービス。"""

    @staticmethod
    def _resolve_due_date(target_year: int, target_month: int, due_day: int) -> date:
        last_day = monthrange(target_year, target_month)[1]
        day = last_day if due_day == _LAST_DAY else min(due_day, last_day)
        return date(target_year, target_month, day)

    @classmethod
    def generate_monthly_tasks(
        cls,
        *,
        target_year: int,
        target_month: int,
        phase: str | None = None,
    ) -> list[TaskSpec]:
        """月次テンプレートからタスク仕様を生成。phase 指定でフェーズを絞り込む。"""
        if not 1 <= target_month <= 12:
            raise ValueError("target_month must be between 1 and 12")
        valid_phases = {MONTHLY_PHASE_OPENING, MONTHLY_PHASE_MIDDLE, MONTHLY_PHASE_CLOSING}
        if phase is not None and phase not in valid_phases:
            raise ValueError(f"unknown phase: {phase}")

        specs: list[TaskSpec] = []
        for template in MONTHLY_TEMPLATES:
            if phase is not None and template.phase != phase:
                continue
            specs.append(
                TaskSpec(
                    task_type=template.task_type,
                    title=template.title,
                    due_date=cls._resolve_due_date(target_year, target_month, template.due_day),
                )
            )
        return specs

    @classmethod
    def generate_daily_tasks(cls, *, target_date: date) -> list[TaskSpec]:
        """日次テンプレートからタスク仕様を生成（締日は当日）。"""
        return [
            TaskSpec(task_type=task_type, title=title, due_date=target_date)
            for task_type, title in DAILY_TEMPLATES
        ]

    @staticmethod
    def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
        index = (month - 1) + delta
        return year + index // 12, index % 12 + 1

    @classmethod
    def generate_annual_tasks(
        cls,
        *,
        calendar_year: int,
        fiscal_year_end_month: int | None = None,
    ) -> list[TaskSpec]:
        """年次の法定イベントを生成。fiscal_year_end_month 指定時は
        法人税・消費税の確定申告（事業年度終了日の翌日から2ヶ月以内）を追加する。"""
        specs = [
            TaskSpec(
                task_type=template.task_type,
                title=template.title,
                due_date=date(calendar_year, template.month, template.day),
            )
            for template in ANNUAL_FIXED_TEMPLATES
        ]

        if fiscal_year_end_month is not None:
            if not 1 <= fiscal_year_end_month <= 12:
                raise ValueError("fiscal_year_end_month must be between 1 and 12")
            # 事業年度終了日（当該月末）の2ヶ月後を申告期限とする（法人税法74条）。
            filing_year, filing_month = cls._add_months(calendar_year, fiscal_year_end_month, 2)
            filing_day = monthrange(filing_year, filing_month)[1]
            specs.append(
                TaskSpec(
                    task_type="corporate_tax_return",
                    title="法人税・消費税 確定申告",
                    due_date=date(filing_year, filing_month, filing_day),
                )
            )
        return specs
