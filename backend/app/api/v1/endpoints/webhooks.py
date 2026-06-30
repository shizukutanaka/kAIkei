from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import WebhookDelivery, WebhookEndpoint
from app.schemas.schemas import (
    WebhookDeliveryResponse,
    WebhookEndpointCreate,
    WebhookEndpointResponse,
)

router = APIRouter()


@router.post("/endpoints", response_model=WebhookEndpointResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook_endpoint(
    payload: WebhookEndpointCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> WebhookEndpointResponse:
    endpoint = WebhookEndpoint(
        company_id=payload.company_id,
        target_url=payload.target_url,
        secret_token=payload.secret_token,
        subscribed_events=payload.subscribed_events,
    )
    db.add(endpoint)
    await db.flush()
    await db.refresh(endpoint)
    return WebhookEndpointResponse.model_validate(endpoint)


@router.get("/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_webhook_deliveries(
    company_id: UUID = Query(...),  # noqa: B008
    status_filter: str | None = Query(None, alias="status"),  # noqa: B008
    endpoint_id: UUID | None = Query(None),  # noqa: B008
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[WebhookDeliveryResponse]:
    stmt = select(WebhookDelivery).where(WebhookDelivery.company_id == company_id)
    if status_filter is not None:
        stmt = stmt.where(WebhookDelivery.status == status_filter)
    if endpoint_id is not None:
        stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
    stmt = stmt.order_by(WebhookDelivery.created_at.desc())
    result = await db.execute(stmt)
    return [WebhookDeliveryResponse.model_validate(item) for item in result.scalars().all()]
