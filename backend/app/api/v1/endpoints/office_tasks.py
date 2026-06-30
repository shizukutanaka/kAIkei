from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import OfficeTask
from app.schemas.schemas import (
    OfficeTaskGenerateRequest,
    OfficeTaskResponse,
    OfficeTaskStatusUpdate,
)
from app.services.task_template import TaskSpec, TaskTemplateService

router = APIRouter()

_VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled"}


def _build_specs(payload: OfficeTaskGenerateRequest) -> list[TaskSpec]:
    if payload.scope == "monthly":
        if payload.target_year is None or payload.target_month is None:
            raise HTTPException(status_code=422, detail="target_year and target_month are required for monthly scope")
        try:
            return TaskTemplateService.generate_monthly_tasks(
                target_year=payload.target_year,
                target_month=payload.target_month,
                phase=payload.phase,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.scope == "daily":
        if payload.target_date is None:
            raise HTTPException(status_code=422, detail="target_date is required for daily scope")
        return TaskTemplateService.generate_daily_tasks(target_date=payload.target_date)
    raise HTTPException(status_code=422, detail="scope must be 'monthly' or 'daily'")


@router.post("/generate", response_model=list[OfficeTaskResponse], status_code=status.HTTP_201_CREATED)
async def generate_office_tasks(
    payload: OfficeTaskGenerateRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[OfficeTaskResponse]:
    specs = _build_specs(payload)
    tasks = [
        OfficeTask(
            company_id=payload.company_id,
            task_type=spec.task_type,
            title=spec.title,
            due_date=spec.due_date,
        )
        for spec in specs
    ]
    db.add_all(tasks)
    await db.commit()
    for task in tasks:
        await db.refresh(task)
    return [OfficeTaskResponse.model_validate(task) for task in tasks]


@router.get("", response_model=list[OfficeTaskResponse])
async def list_office_tasks(
    company_id: UUID = Query(...),  # noqa: B008
    status_filter: str | None = Query(None, alias="status"),  # noqa: B008
    task_type: str | None = Query(None),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[OfficeTaskResponse]:
    stmt = select(OfficeTask).where(OfficeTask.company_id == company_id)
    if status_filter is not None:
        stmt = stmt.where(OfficeTask.status == status_filter)
    if task_type is not None:
        stmt = stmt.where(OfficeTask.task_type == task_type)
    stmt = stmt.order_by(OfficeTask.due_date.asc(), OfficeTask.created_at.asc())
    result = await db.execute(stmt)
    return [OfficeTaskResponse.model_validate(task) for task in result.scalars().all()]


@router.patch("/{task_id}", response_model=OfficeTaskResponse)
async def update_office_task_status(
    task_id: UUID,
    payload: OfficeTaskStatusUpdate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> OfficeTaskResponse:
    if payload.status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status: {payload.status}")
    result = await db.execute(select(OfficeTask).where(OfficeTask.task_id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Office task not found")

    task.status = payload.status
    task.completed_at = datetime.now(UTC) if payload.status == "completed" else None
    await db.commit()
    await db.refresh(task)
    return OfficeTaskResponse.model_validate(task)
