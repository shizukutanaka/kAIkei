from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_permission
from app.core.rbac import Permission
from app.models.models import Employee, AttendanceRecord
from app.schemas.schemas import (
    AttendanceClockInRequest,
    AttendanceClockOutRequest,
    AttendanceManualRequest,
    AttendanceResponse,
    AttendanceListResponse,
)

router = APIRouter()

STANDARD_WORK_MINUTES = 480  # 8h
OVERTIME_THRESHOLD = 480


def _to_response(rec: AttendanceRecord, emp_name: str | None = None) -> AttendanceResponse:
    return AttendanceResponse(
        attendance_id=rec.attendance_id,
        employee_id=rec.employee_id,
        company_id=rec.company_id,
        work_date=rec.work_date,
        clock_in=rec.clock_in,
        clock_out=rec.clock_out,
        break_minutes=rec.break_minutes,
        work_minutes=rec.work_minutes,
        overtime_minutes=rec.overtime_minutes,
        leave_type=rec.leave_type,
        note=rec.note,
        employee_name=emp_name,
    )


def _calc_work_minutes(clock_in: datetime, clock_out: datetime, break_minutes: int) -> tuple[int, int]:
    total = int((clock_out - clock_in).total_seconds() / 60)
    work = max(total - break_minutes, 0)
    overtime = max(work - OVERTIME_THRESHOLD, 0)
    return work, overtime


@router.post("/clock-in", response_model=AttendanceResponse)
async def clock_in(
    payload: AttendanceClockInRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> AttendanceResponse:
    """出勤打刻。"""
    today = date.today()
    existing = await db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == payload.employee_id,
            AttendanceRecord.work_date == today,
        )
    )
    rec = existing.scalar_one_or_none()
    if rec and rec.clock_in:
        raise HTTPException(status_code=409, detail="本日はすでに出勤打刻済みです")
    now = datetime.now()
    if rec:
        rec.clock_in = now
    else:
        rec = AttendanceRecord(
            employee_id=payload.employee_id,
            company_id=payload.company_id,
            work_date=today,
            clock_in=now,
            leave_type="none",
        )
        db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return _to_response(rec)


@router.post("/clock-out", response_model=AttendanceResponse)
async def clock_out(
    payload: AttendanceClockOutRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> AttendanceResponse:
    """退勤打刻。"""
    today = date.today()
    result = await db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == payload.employee_id,
            AttendanceRecord.work_date == today,
        )
    )
    rec = result.scalar_one_or_none()
    if not rec or not rec.clock_in:
        raise HTTPException(status_code=400, detail="出勤打刻がありません")
    if rec.clock_out:
        raise HTTPException(status_code=409, detail="本日はすでに退勤打刻済みです")
    now = datetime.now()
    rec.clock_out = now
    work, overtime = _calc_work_minutes(rec.clock_in, now, rec.break_minutes)
    rec.work_minutes = work
    rec.overtime_minutes = overtime
    await db.commit()
    await db.refresh(rec)
    return _to_response(rec)


@router.post("/manual", response_model=AttendanceResponse, status_code=201)
async def create_manual_attendance(
    payload: AttendanceManualRequest,
    current_user: CurrentUser = Depends(require_permission(Permission.JOURNAL_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> AttendanceResponse:
    """手動で勤怠記録を作成する。"""
    existing = await db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == payload.employee_id,
            AttendanceRecord.work_date == payload.work_date,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="該当日の勤怠記録がすでに存在します")

    work_minutes = 0
    overtime_minutes = 0
    if payload.clock_in and payload.clock_out:
        work_minutes, overtime_minutes = _calc_work_minutes(
            payload.clock_in, payload.clock_out, payload.break_minutes
        )

    rec = AttendanceRecord(
        employee_id=payload.employee_id,
        company_id=payload.company_id,
        work_date=payload.work_date,
        clock_in=payload.clock_in,
        clock_out=payload.clock_out,
        break_minutes=payload.break_minutes,
        work_minutes=work_minutes,
        overtime_minutes=overtime_minutes,
        leave_type=payload.leave_type,
        note=payload.note,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return _to_response(rec)


@router.get("/records", response_model=AttendanceListResponse)
async def list_attendance(
    company_id: UUID = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    employee_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> AttendanceListResponse:
    """指定期間の勤怠記録を取得する。"""
    conditions = [
        AttendanceRecord.company_id == company_id,
        AttendanceRecord.work_date >= start_date,
        AttendanceRecord.work_date <= end_date,
    ]
    if employee_id:
        conditions.append(AttendanceRecord.employee_id == employee_id)
    count_result = await db.execute(
        select(func.count()).select_from(AttendanceRecord).where(*conditions)
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(AttendanceRecord, Employee.employee_name)
        .join(Employee, AttendanceRecord.employee_id == Employee.employee_id)
        .where(*conditions)
        .order_by(AttendanceRecord.work_date, Employee.employee_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()
    items = [_to_response(rec, name) for rec, name in rows]
    return AttendanceListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/summary", response_model=list[dict])
async def attendance_summary(
    company_id: UUID = Query(...),
    year: int = Query(...),
    month: int = Query(...),
    current_user: CurrentUser = Depends(require_permission(Permission.REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """月次勤怠サマリー（従業員ごとの集計）。"""
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    result = await db.execute(
        select(
            AttendanceRecord.employee_id,
            Employee.employee_name,
            Employee.employee_code,
            func.count(AttendanceRecord.attendance_id).label("days"),
            func.coalesce(func.sum(AttendanceRecord.work_minutes), 0).label("total_work_minutes"),
            func.coalesce(func.sum(AttendanceRecord.overtime_minutes), 0).label("total_overtime_minutes"),
            func.count().filter(AttendanceRecord.leave_type == "paid_leave").label("paid_leave_days"),
            func.count().filter(AttendanceRecord.leave_type == "absent").label("absent_days"),
        )
        .join(Employee, AttendanceRecord.employee_id == Employee.employee_id)
        .where(
            AttendanceRecord.company_id == company_id,
            AttendanceRecord.work_date >= start,
            AttendanceRecord.work_date <= end,
        )
        .group_by(AttendanceRecord.employee_id, Employee.employee_name, Employee.employee_code)
        .order_by(Employee.employee_code)
    )
    rows = result.all()
    return [
        {
            "employee_id": str(row.employee_id),
            "employee_name": row.employee_name,
            "employee_code": row.employee_code,
            "days": row.days,
            "total_work_minutes": row.total_work_minutes,
            "total_overtime_minutes": row.total_overtime_minutes,
            "paid_leave_days": row.paid_leave_days,
            "absent_days": row.absent_days,
        }
        for row in rows
    ]
