from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.core.rbac import Permission
from app.models.models import JournalHeader, JournalLine
from app.schemas.schemas import JournalCreate, JournalListResponse, JournalResponse
from app.services.journal_service import JournalService
from app.services.validation_engine import ValidationError, ValidationEngine

router = APIRouter()


@router.post("", response_model=JournalResponse, status_code=status.HTTP_201_CREATED)
async def create_journal(
    payload: JournalCreate,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> JournalHeader:
    """Create a new journal entry after validation."""
    try:
        ValidationEngine.validate(payload, created_by=current_user.user_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message, "field": e.field})

    count_result = await db.execute(
        select(func.count()).select_from(JournalHeader).where(JournalHeader.company_id == payload.company_id)
    )
    count = count_result.scalar() or 0
    journal_number = f"JRN-{count + 1:08d}"

    header = JournalHeader(
        company_id=payload.company_id,
        journal_number=journal_number,
        transaction_date=payload.transaction_date,
        voucher_type=payload.voucher_type,
        summary=payload.summary,
        approval_status="draft",
        created_by=current_user.user_id,
    )
    db.add(header)
    await db.flush()

    for i, line in enumerate(payload.lines, start=1):
        db.add(
            JournalLine(
                journal_header_id=header.journal_header_id,
                line_number=i,
                debit_credit=line.debit_credit,
                account_id=line.account_id,
                sub_account_id=line.sub_account_id,
                department_id=line.department_id,
                tax_rule_id=line.tax_rule_id,
                amount=line.amount,
                tax_amount=line.tax_amount,
                description=line.description,
            )
        )

    await db.flush()
    await db.refresh(header)
    return header


@router.get("", response_model=JournalListResponse)
async def list_journals(
    company_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_READ)),
    db: AsyncSession = Depends(get_db),
) -> JournalListResponse:
    """List journals for a company with pagination."""
    offset = (page - 1) * page_size
    result = await db.execute(
        select(JournalHeader)
        .where(JournalHeader.company_id == company_id, JournalHeader.is_deleted == False)  # noqa: E712
        .order_by(JournalHeader.transaction_date.desc(), JournalHeader.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = result.scalars().all()

    count_result = await db.execute(
        select(func.count())
        .select_from(JournalHeader)
        .where(JournalHeader.company_id == company_id, JournalHeader.is_deleted == False)  # noqa: E712
    )
    total = count_result.scalar() or 0

    return JournalListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{journal_header_id}", response_model=JournalResponse)
async def get_journal(
    journal_header_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_READ)),
    db: AsyncSession = Depends(get_db),
) -> JournalHeader:
    result = await db.execute(
        select(JournalHeader).where(
            JournalHeader.journal_header_id == journal_header_id,
            JournalHeader.is_deleted == False,  # noqa: E712
        )
    )
    journal = result.scalar_one_or_none()
    if not journal:
        raise HTTPException(status_code=404, detail="Journal not found")
    return journal


@router.put("/{journal_header_id}/void", response_model=JournalResponse)
async def void_journal(
    journal_header_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_VOID)),
    db: AsyncSession = Depends(get_db),
) -> JournalHeader:
    result = await db.execute(
        select(JournalHeader).where(
            JournalHeader.journal_header_id == journal_header_id,
            JournalHeader.is_deleted == False,  # noqa: E712
        )
    )
    journal = result.scalar_one_or_none()
    if not journal:
        raise HTTPException(status_code=404, detail="Journal not found")
    if journal.is_voided:
        raise HTTPException(status_code=409, detail="Journal is already voided")

    journal.is_voided = True
    await db.flush()
    await db.refresh(journal)
    return journal


@router.put("/{journal_header_id}/approve", response_model=JournalResponse)
async def approve_journal(
    journal_header_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> JournalHeader:
    """Approve a journal entry (SoD check enforced)."""
    try:
        return await JournalService.approve_journal(db, journal_header_id, current_user.user_id)
    except ValidationError as e:
        raise HTTPException(status_code=403, detail={"code": e.code, "message": e.message})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{journal_header_id}/post", response_model=JournalResponse)
async def post_journal(
    journal_header_id: UUID,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_POST)),
    db: AsyncSession = Depends(get_db),
) -> JournalHeader:
    """Post an approved journal entry and update monthly balances."""
    try:
        return await JournalService.post_journal(db, journal_header_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
