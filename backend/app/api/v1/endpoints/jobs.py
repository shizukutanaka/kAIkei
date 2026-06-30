from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import JobExecution, ScheduledJob
from app.schemas.schemas import (
    JobExecutionResponse,
    ScheduledJobCreate,
    ScheduledJobResponse,
)
from app.services.job_scheduler import JobSchedulerService

router = APIRouter()


@router.post("", response_model=ScheduledJobResponse, status_code=status.HTTP_201_CREATED)
async def create_scheduled_job(
    payload: ScheduledJobCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ScheduledJobResponse:
    now = datetime.now(UTC)
    try:
        next_run_at = JobSchedulerService.compute_next_run(
            frequency=payload.frequency,
            run_hour=payload.run_hour,
            run_day=payload.run_day,
            after=now,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job = ScheduledJob(
        company_id=payload.company_id,
        job_type=payload.job_type,
        frequency=payload.frequency,
        run_hour=payload.run_hour,
        run_day=payload.run_day,
        priority=payload.priority,
        payload=payload.payload,
        next_run_at=next_run_at,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return ScheduledJobResponse.model_validate(job)


@router.get("", response_model=list[ScheduledJobResponse])
async def list_scheduled_jobs(
    company_id: UUID = Query(...),  # noqa: B008
    is_active: bool | None = Query(None),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[ScheduledJobResponse]:
    stmt = select(ScheduledJob).where(ScheduledJob.company_id == company_id)
    if is_active is not None:
        stmt = stmt.where(ScheduledJob.is_active == is_active)
    stmt = stmt.order_by(ScheduledJob.priority.asc(), ScheduledJob.created_at.asc())
    result = await db.execute(stmt)
    return [ScheduledJobResponse.model_validate(job) for job in result.scalars().all()]


@router.post("/{scheduled_job_id}/run", response_model=JobExecutionResponse, status_code=status.HTTP_201_CREATED)
async def run_scheduled_job(
    scheduled_job_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> JobExecutionResponse:
    job_result = await db.execute(
        select(ScheduledJob).where(ScheduledJob.scheduled_job_id == scheduled_job_id)
    )
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Scheduled job not found")

    running_result = await db.execute(
        select(func.count()).select_from(JobExecution).where(
            JobExecution.scheduled_job_id == scheduled_job_id,
            JobExecution.status == "running",
        )
    )
    running_count = running_result.scalar() or 0
    if not JobSchedulerService.can_claim(running_count):
        raise HTTPException(status_code=409, detail="A job execution is already running")

    execution = JobExecution(
        scheduled_job_id=job.scheduled_job_id,
        company_id=job.company_id,
        job_type=job.job_type,
        status="pending",
        priority=job.priority,
        scheduled_for=datetime.now(UTC),
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return JobExecutionResponse.model_validate(execution)


@router.post("/dispatch", response_model=list[JobExecutionResponse], status_code=status.HTTP_201_CREATED)
async def dispatch_due_jobs(
    company_id: UUID = Query(...),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[JobExecutionResponse]:
    now = datetime.now(UTC)
    jobs_result = await db.execute(
        select(ScheduledJob).where(
            ScheduledJob.company_id == company_id,
            ScheduledJob.is_active == True,  # noqa: E712
        )
    )
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
    return [JobExecutionResponse.model_validate(execution) for execution in created]


@router.get("/executions", response_model=list[JobExecutionResponse])
async def list_job_executions(
    company_id: UUID = Query(...),  # noqa: B008
    status_filter: str | None = Query(None, alias="status"),  # noqa: B008
    scheduled_job_id: UUID | None = Query(None),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[JobExecutionResponse]:
    stmt = select(JobExecution).where(JobExecution.company_id == company_id)
    if status_filter is not None:
        stmt = stmt.where(JobExecution.status == status_filter)
    if scheduled_job_id is not None:
        stmt = stmt.where(JobExecution.scheduled_job_id == scheduled_job_id)
    stmt = stmt.order_by(JobExecution.created_at.desc())
    result = await db.execute(stmt)
    return [JobExecutionResponse.model_validate(execution) for execution in result.scalars().all()]
