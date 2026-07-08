from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import JobExecution, OfficeTask, WebhookDelivery
from app.schemas.schemas import (
    HealthSummaryResponse,
    OperationsHealthResponse,
)
from app.services.operations_monitor import OperationsMonitorService

router = APIRouter()


@router.get("/health", response_model=OperationsHealthResponse)
async def get_operations_health(
    company_id: UUID = Query(...),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> OperationsHealthResponse:
    job_rows = await db.execute(
        select(JobExecution.status).where(JobExecution.company_id == company_id)
    )
    job_summary = OperationsMonitorService.classify_statuses(list(job_rows.scalars().all()))

    webhook_rows = await db.execute(
        select(WebhookDelivery.status).where(WebhookDelivery.company_id == company_id)
    )
    webhook_summary = OperationsMonitorService.classify_statuses(list(webhook_rows.scalars().all()))

    overdue_rows = await db.execute(
        select(OfficeTask.task_id).where(
            OfficeTask.company_id == company_id,
            OfficeTask.status.notin_(["completed", "cancelled"]),
            OfficeTask.due_date < datetime.now(UTC).date(),
        )
    )
    overdue_count = len(list(overdue_rows.scalars().all()))

    overall_level = OperationsMonitorService.aggregate_levels(
        [
            job_summary.level,
            webhook_summary.level,
            OperationsMonitorService.overdue_task_level(overdue_count),
        ]
    )

    return OperationsHealthResponse(
        company_id=company_id,
        overall_level=overall_level,
        jobs=HealthSummaryResponse(**vars(job_summary)),
        webhooks=HealthSummaryResponse(**vars(webhook_summary)),
        overdue_tasks=overdue_count,
    )
