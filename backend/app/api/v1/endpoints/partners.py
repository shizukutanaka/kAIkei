from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Partner
from app.schemas.schemas import PartnerCreate, PartnerUpdate, PartnerResponse

router = APIRouter()


def _to_response(p: Partner) -> PartnerResponse:
    return PartnerResponse(
        partner_id=p.partner_id,
        company_id=p.company_id,
        partner_code=p.partner_code,
        partner_name=p.partner_name,
        partner_type=p.partner_type,
        postal_code=p.postal_code,
        address=p.address,
        phone=p.phone,
        email=p.email,
        contact_person=p.contact_person,
        payment_terms=p.payment_terms,
        is_active=p.is_active,
    )


@router.get("", response_model=list[PartnerResponse])
async def list_partners(
    company_id: UUID = Query(...),
    partner_type: str | None = Query(None),
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[PartnerResponse]:
    stmt = select(Partner).where(
        Partner.company_id == company_id,
        Partner.is_deleted == False,  # noqa: E712
    )
    if partner_type:
        stmt = stmt.where(Partner.partner_type == partner_type)
    stmt = stmt.order_by(Partner.partner_code)
    result = await db.execute(stmt)
    partners = result.scalars().all()
    return [_to_response(p) for p in partners]


@router.post("", response_model=PartnerResponse, status_code=status.HTTP_201_CREATED)
async def create_partner(
    payload: PartnerCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> PartnerResponse:
    existing = await db.execute(
        select(Partner).where(
            Partner.company_id == payload.company_id,
            Partner.partner_code == payload.partner_code,
            Partner.is_deleted == False,  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="この取引先コードは既に存在します")

    partner = Partner(
        company_id=payload.company_id,
        partner_code=payload.partner_code,
        partner_name=payload.partner_name,
        partner_type=payload.partner_type,
        postal_code=payload.postal_code,
        address=payload.address,
        phone=payload.phone,
        email=payload.email,
        contact_person=payload.contact_person,
        payment_terms=payload.payment_terms,
    )
    db.add(partner)
    await db.commit()
    await db.refresh(partner)
    return _to_response(partner)


@router.put("/{partner_id}", response_model=PartnerResponse)
async def update_partner(
    partner_id: UUID,
    payload: PartnerUpdate,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> PartnerResponse:
    result = await db.execute(
        select(Partner).where(
            Partner.partner_id == partner_id,
            Partner.is_deleted == False,  # noqa: E712
        )
    )
    partner = result.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="取引先が見つかりません")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(partner, field, value)

    await db.commit()
    await db.refresh(partner)
    return _to_response(partner)


@router.delete("/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_partner(
    partner_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.MASTER_DELETE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Partner).where(
            Partner.partner_id == partner_id,
            Partner.is_deleted == False,  # noqa: E712
        )
    )
    partner = result.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="取引先が見つかりません")
    partner.is_deleted = True
    partner.is_active = False
    await db.commit()
