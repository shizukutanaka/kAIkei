"""スケジュールジョブのディスパッチ（due判定→JobExecution作成）。

APIエンドポイント（会社単位・手動）と定期バックグラウンドワーカー（全社横断・自動）の
双方から再利用する。due判定・多重防止・次回実行時刻の計算は純粋な JobSchedulerService に
委譲し、本モジュールはDBアクセス（対象取得・pending作成・next_run_at更新）のみを担う。

ここで作成するのは status="pending" の JobExecution 行のみで、副作用のある実処理は行わない
（実行は外部ワーカーが /jobs/executions/{id}/start・complete API を通じて進める既存設計）。
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import JobExecution, ScheduledJob
from app.services.job_scheduler import JobSchedulerService


async def dispatch_due_jobs(
    db: AsyncSession, company_id: UUID | None = None
) -> list[JobExecution]:
    """実行時刻に達したアクティブなScheduledJobにpendingなJobExecutionを作成する。

    company_id指定時はその会社のみ、Noneのときは全社横断（定期ワーカー用）。
    実行中(running)のジョブがある種別はcan_claimで多重ディスパッチを防ぐ。
    ディスパッチしたジョブはlast_run_at/next_run_atを更新し、次周期まで再ディスパッチしない。
    """
    now = datetime.now(UTC)
    stmt = select(ScheduledJob).where(ScheduledJob.is_active == True)  # noqa: E712
    if company_id is not None:
        stmt = stmt.where(ScheduledJob.company_id == company_id)
    jobs_result = await db.execute(stmt)
    due_jobs = JobSchedulerService.select_due_jobs(list(jobs_result.scalars().all()), now=now)

    created: list[JobExecution] = []
    for job in due_jobs:
        running_result = await db.execute(
            select(func.count()).select_from(JobExecution).where(
                JobExecution.scheduled_job_id == job.scheduled_job_id,
                JobExecution.status == "running",
            )
        )
        if not JobSchedulerService.can_claim(running_result.scalar() or 0):
            continue
        execution = JobExecution(
            scheduled_job_id=job.scheduled_job_id,
            company_id=job.company_id,
            job_type=job.job_type,
            status="pending",
            priority=job.priority,
            scheduled_for=now,
        )
        db.add(execution)
        created.append(execution)
        job.last_run_at = now
        job.next_run_at = JobSchedulerService.compute_next_run(
            frequency=job.frequency,
            run_hour=job.run_hour,
            run_day=job.run_day,
            after=now,
        )
    await db.commit()
    for execution in created:
        await db.refresh(execution)
    return created
