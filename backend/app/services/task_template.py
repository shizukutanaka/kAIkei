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
