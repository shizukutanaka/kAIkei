from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.schemas.schemas import (
    WebhookDeliveryResponse,
    WebhookEndpointCreate,
    WebhookEndpointResponse,
)
from app.services import webhook_service

router = APIRouter()


@router.post("", response_model=WebhookEndpointResponse, status_code=status.HTTP_201_CREATED)
async def register_endpoint(
    payload: WebhookEndpointCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.WEBHOOK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> WebhookEndpointResponse:
    """Webhook登録先を作成する。"""
    try:
        endpoint = await webhook_service.create_endpoint(
            db,
            tenant_id=current_user.tenant_id,
            url=payload.url,
            secret=payload.secret,
            subscribed_events=payload.subscribed_events,
            company_id=payload.company_id,
            description=payload.description,
        )
    except webhook_service.UnsafeWebhookUrlError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return WebhookEndpointResponse.model_validate(endpoint)


@router.get("", response_model=list[WebhookEndpointResponse])
async def list_endpoints(
    company_id: UUID | None = Query(None),
    active_only: bool = Query(False),
    current_user: CurrentUser = Depends(require_permission(Permission.WEBHOOK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookEndpointResponse]:
    """Webhook登録先を一覧取得する。"""
    endpoints = await webhook_service.list_endpoints(
        db, tenant_id=current_user.tenant_id, company_id=company_id, active_only=active_only
    )
    return [WebhookEndpointResponse.model_validate(e) for e in endpoints]


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(
    endpoint_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.WEBHOOK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Webhook登録先を削除する。"""
    deleted = await webhook_service.delete_endpoint(db, endpoint_id, current_user.tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")


@router.get("/{endpoint_id}/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_deliveries(
    endpoint_id: UUID,
    delivery_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission(Permission.WEBHOOK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookDeliveryResponse]:
    """Webhook配信履歴を取得する。"""
    endpoint = await webhook_service.get_endpoint(db, endpoint_id, current_user.tenant_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    deliveries = await webhook_service.list_deliveries(db, endpoint_id, status=delivery_status, limit=limit)
    return [WebhookDeliveryResponse.model_validate(d) for d in deliveries]


@router.post("/process")
async def process_due_deliveries(
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission(Permission.WEBHOOK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """再試行時刻を過ぎた保留中の配信を処理する（配信ワーカーの手動トリガー）。

    自テナントのエンドポイント宛ての配信のみを処理する（他テナントの配信を
    強制送信できてしまわないよう、常にtenant_idでスコープする）。
    """
    processed = await webhook_service.process_due_deliveries(
        db, limit=limit, tenant_id=current_user.tenant_id
    )
    return {"processed": processed}


@router.post("/deliveries/{delivery_id}/replay", response_model=WebhookDeliveryResponse)
async def replay_delivery(
    delivery_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.WEBHOOK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> WebhookDeliveryResponse:
    """失敗した配信を再キューする（再送）。"""
    delivery = await webhook_service.replay_delivery(db, delivery_id, current_user.tenant_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="Webhook delivery not found")
    return WebhookDeliveryResponse.model_validate(delivery)
