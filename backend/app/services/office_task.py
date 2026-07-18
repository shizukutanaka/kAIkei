"""月次業務エンジン・事務タスクサービス（フェーズ8）。

月次決算等の定型業務をテンプレートから対象月のタスクとして生成し、期日計算・
進捗集計を行う。

テンプレート展開・期日計算・進捗集計の中核はDB非依存の純粋関数として切り出す。
"""
import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import OfficeTask

logger = logging.getLogger(__name__)

VALID_STATUSES = {"todo", "in_progress", "done"}


@dataclass
class TaskTemplate:
    """月次タスクのテンプレート。"""
    title: str
    task_type: str
    day_of_month: int  # 期日の日（月末超過は自動的に月末へ丸める）


# 既定の月次決算タスクテンプレート。
DEFAULT_MONTHLY_CLOSE_TEMPLATES: list[TaskTemplate] = [
    TaskTemplate("入出金明細の取込", "monthly_close", 3),
    TaskTemplate("経費精算の締め", "monthly_close", 5),
    TaskTemplate("銀行残高の照合・消込", "monthly_close", 7),
    TaskTemplate("仕訳の最終確認", "monthly_close", 8),
    TaskTemplate("月次試算表の確定", "monthly_close", 10),
]


# --- 純粋関数（DB非依存・テスト可能） ---------------------------------------

def compute_due_date(year: int, month: int, day_of_month: int) -> date:
    """対象月における期日を計算する。月の日数を超える日は月末へ丸める。"""
    last_day = calendar.monthrange(year, month)[1]
    day = max(1, min(day_of_month, last_day))
    return date(year, month, day)


def period_label(year: int, month: int) -> str:
    """対象月を "YYYY-MM" 形式のラベルにする。"""
    return f"{year:04d}-{month:02d}"


def generate_monthly_tasks(
    templates: list[TaskTemplate], year: int, month: int
) -> list[dict]:
    """テンプレートから対象月のタスク定義（dict）を生成する。"""
    period = period_label(year, month)
    return [
        {
            "title": tmpl.title,
            "task_type": tmpl.task_type,
            "due_date": compute_due_date(year, month, tmpl.day_of_month),
            "period": period,
            "status": "todo",
        }
        for tmpl in templates
    ]


def progress_summary(statuses: list[str]) -> dict:
    """タスクステータス列から進捗サマリーを集計する。"""
    total = len(statuses)
    done = sum(1 for s in statuses if s == "done")
    in_progress = sum(1 for s in statuses if s == "in_progress")
    todo = sum(1 for s in statuses if s == "todo")
    return {
        "total": total,
        "todo": todo,
        "in_progress": in_progress,
        "done": done,
        "completion_rate": round(done / total, 4) if total else 0.0,
    }


# --- 非同期サービス（DB依存） ------------------------------------------------

async def generate_from_templates(
    db: AsyncSession,
    tenant_id: UUID,
    company_id: UUID,
    year: int,
    month: int,
    templates: list[TaskTemplate] | None = None,
) -> list[OfficeTask]:
    """対象月の月次タスクを生成して登録する（重複期間はスキップ）。"""
    templates = templates or DEFAULT_MONTHLY_CLOSE_TEMPLATES
    period = period_label(year, month)

    existing_result = await db.execute(
        select(OfficeTask.title).where(
            OfficeTask.company_id == company_id,
            OfficeTask.period == period,
        )
    )
    existing_titles = {t for (t,) in existing_result.all()}

    created: list[OfficeTask] = []
    for spec in generate_monthly_tasks(templates, year, month):
        if spec["title"] in existing_titles:
            continue
        task = OfficeTask(
            tenant_id=tenant_id,
            company_id=company_id,
            title=spec["title"],
            task_type=spec["task_type"],
            due_date=spec["due_date"],
            period=spec["period"],
            status="todo",
        )
        db.add(task)
        created.append(task)

    if created:
        await db.commit()
        for task in created:
            await db.refresh(task)
    return created


async def list_tasks(
    db: AsyncSession,
    company_id: UUID,
    period: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[OfficeTask]:
    """事務タスクを一覧取得する。"""
    conditions = [OfficeTask.company_id == company_id]
    if period is not None:
        conditions.append(OfficeTask.period == period)
    if status is not None:
        conditions.append(OfficeTask.status == status)
    result = await db.execute(
        select(OfficeTask).where(*conditions).order_by(OfficeTask.due_date).limit(limit)
    )
    return list(result.scalars().all())


async def create_task(
    db: AsyncSession,
    tenant_id: UUID,
    company_id: UUID,
    title: str,
    task_type: str,
    due_date: date | None = None,
    assigned_to: UUID | None = None,
    period: str | None = None,
) -> OfficeTask:
    """事務タスクを個別に作成する。"""
    task = OfficeTask(
        tenant_id=tenant_id,
        company_id=company_id,
        title=title,
        task_type=task_type,
        due_date=due_date,
        assigned_to=assigned_to,
        period=period,
        status="todo",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def update_status(
    db: AsyncSession, company_id: UUID, task_id: UUID, new_status: str
) -> OfficeTask | None:
    """タスクのステータスを更新する。doneにした場合はcompleted_atを記録する。"""
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")
    result = await db.execute(
        select(OfficeTask).where(
            OfficeTask.office_task_id == task_id,
            OfficeTask.company_id == company_id,
        )
    )
    task = result.scalar_one_or_none()
    if task is None:
        return None
    task.status = new_status
    task.completed_at = datetime.now(timezone.utc) if new_status == "done" else None
    await db.commit()
    await db.refresh(task)
    return task


async def get_progress(db: AsyncSession, company_id: UUID, period: str) -> dict:
    """対象期間の進捗サマリーを取得する。"""
    tasks = await list_tasks(db, company_id, period=period, limit=1000)
    return progress_summary([t.status for t in tasks])
