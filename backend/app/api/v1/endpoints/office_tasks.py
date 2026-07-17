from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rbac import Permission
from app.schemas.schemas import (
    OfficeTaskCreate,
    OfficeTaskGenerateRequest,
    OfficeTaskProgressResponse,
    OfficeTaskResponse,
    OfficeTaskStatusUpdate,
)
from app.services import office_task

router = APIRouter()


@router.post("/generate", response_model=list[OfficeTaskResponse], status_code=status.HTTP_201_CREATED)
async def generate(
    payload: OfficeTaskGenerateRequest,
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> list[OfficeTaskResponse]:
    """対象月の月次業務タスクをテンプレートから生成する。"""
    tasks = await office_task.generate_from_templates(
        db,
        tenant_id=current_user.tenant_id,
        company_id=company_id,
        year=payload.year,
        month=payload.month,
    )
    return [OfficeTaskResponse.model_validate(t) for t in tasks]


@router.post("", response_model=OfficeTaskResponse, status_code=status.HTTP_201_CREATED)
async def create(
    payload: OfficeTaskCreate,
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> OfficeTaskResponse:
    """事務タスクを個別に作成する。"""
    task = await office_task.create_task(
        db,
        tenant_id=current_user.tenant_id,
        company_id=company_id,
        title=payload.title,
        task_type=payload.task_type,
        due_date=payload.due_date,
        assigned_to=payload.assigned_to,
        period=payload.period,
    )
    return OfficeTaskResponse.model_validate(task)


@router.get("", response_model=list[OfficeTaskResponse])
async def list_tasks(
    company_id: UUID = Query(...),
    period: str | None = Query(None),
    task_status: str | None = Query(None, alias="status"),
    limit: int = Query(200, ge=1, le=1000),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OfficeTaskResponse]:
    """事務タスクを一覧取得する。"""
    tasks = await office_task.list_tasks(
        db, company_id=company_id, period=period, status=task_status, limit=limit
    )
    return [OfficeTaskResponse.model_validate(t) for t in tasks]


@router.get("/progress", response_model=OfficeTaskProgressResponse)
async def progress(
    company_id: UUID = Query(...),
    period: str = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OfficeTaskProgressResponse:
    """対象期間の月次業務進捗を取得する。"""
    result = await office_task.get_progress(db, company_id=company_id, period=period)
    return OfficeTaskProgressResponse(**result)


@router.patch("/{task_id}", response_model=OfficeTaskResponse)
async def update_status(
    task_id: UUID,
    payload: OfficeTaskStatusUpdate,
    company_id: UUID = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OfficeTaskResponse:
    """タスクのステータスを更新する。"""
    task = await office_task.update_status(
        db, company_id=company_id, task_id=task_id, new_status=payload.status
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Office task not found")
    return OfficeTaskResponse.model_validate(task)
