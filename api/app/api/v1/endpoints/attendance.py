from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_manager, require_staff
from app.db.database import get_db
from app.models.models import AttendanceRecord, User, WorkerProfile
from app.schemas.attendance import (
    AttendanceOut,
    AttendanceStatusOut,
    ClockInRequest,
    ClockOutRequest,
)
from app.services.attendance_location import assert_clock_location_within_ward_boundaries

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.post(
    "/clock-in",
    response_model=AttendanceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start your workday",
    description="Clock in with GPS. Location must fall within Delhi ward boundaries (and your assigned ward if set).",
    operation_id="attendanceClockIn",
    response_description="Attendance record with clock-in time and location.",
)
async def clock_in(
    body: ClockInRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    today = date.today()
    existing = await db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.user_id == user.id,
            AttendanceRecord.date == today,
            AttendanceRecord.clock_out_time.is_(None),
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Already clocked in today")

    lat_f = float(body.lat)
    lng_f = float(body.lng)
    await assert_clock_location_within_ward_boundaries(db, user, lat_f, lng_f)

    print(f"[DEBUG] Attendance: User {user.id} clock-in at ({body.lat}, {body.lng})")
    now = datetime.now(timezone.utc)
    record = AttendanceRecord(
        user_id=user.id,
        date=today,
        clock_in_time=now,
        clock_in_lat=body.lat,
        clock_in_lng=body.lng,
    )
    db.add(record)

    if user.worker_profile:
        user.worker_profile.current_status = "onDuty"
        user.worker_profile.last_active_lat = body.lat
        user.worker_profile.last_active_lng = body.lng

    await db.commit()
    await db.refresh(record)
    return AttendanceOut.model_validate(record)


@router.post(
    "/clock-out",
    response_model=AttendanceOut,
    summary="Finish your workday",
    description="Clock out with GPS. Location must fall within Delhi ward boundaries (and your assigned ward if set).",
    operation_id="attendanceClockOut",
    response_description="Attendance record with clock-out and duration.",
)
async def clock_out(
    body: ClockOutRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    result = await db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.user_id == user.id,
            AttendanceRecord.clock_out_time.is_(None),
        ).order_by(AttendanceRecord.clock_in_time.desc()).limit(1)
    )
    record = result.scalar_one_or_none()
    if not record:
        # Log to help debug clock-out 404 (e.g. clock-in not persisted, auth mismatch)
        print(f"[DEBUG] Attendance: User {user.id} clock-out 404 — no active record found")
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active clock-in found")

    lat_f = float(body.lat)
    lng_f = float(body.lng)
    await assert_clock_location_within_ward_boundaries(db, user, lat_f, lng_f)

    print(f"[DEBUG] Attendance: User {user.id} clock-out at ({body.lat}, {body.lng})")
    now = datetime.now(timezone.utc)
    record.clock_out_time = now
    record.clock_out_lat = body.lat
    record.clock_out_lng = body.lng

    clock_in_utc = record.clock_in_time
    if clock_in_utc.tzinfo is None:
        clock_in_utc = clock_in_utc.replace(tzinfo=timezone.utc)
    record.total_duration_seconds = int((now - clock_in_utc).total_seconds())

    if user.worker_profile:
        user.worker_profile.current_status = "offDuty"

    await db.commit()
    await db.refresh(record)
    return AttendanceOut.model_validate(record)


@router.get(
    "/status",
    response_model=AttendanceStatusOut,
    summary="Check your current status",
    description="See if you are currently clocked in and view your record for today.",
    operation_id="getAttendanceCurrentStatus",
    response_description="Is clocked in and current record if any.",
)
async def attendance_status(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    result = await db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.user_id == user.id,
            AttendanceRecord.clock_out_time.is_(None),
        ).order_by(AttendanceRecord.clock_in_time.desc()).limit(1)
    )
    record = result.scalar_one_or_none()
    return AttendanceStatusOut(
        is_clocked_in=record is not None,
        current_record=AttendanceOut.model_validate(record) if record else None,
    )


@router.get(
    "/history",
    response_model=list[AttendanceOut],
    summary="View your work history",
    description="Look back at your attendance records. Optional from_date/to_date filter.",
    operation_id="getAttendanceHistoryLog",
)
async def attendance_history(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
    from_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    q = select(AttendanceRecord).where(AttendanceRecord.user_id == user.id)
    if from_date:
        q = q.where(AttendanceRecord.date >= from_date)
    if to_date:
        q = q.where(AttendanceRecord.date <= to_date)
    q = q.order_by(AttendanceRecord.date.desc()).limit(90)
    result = await db.execute(q)
    records = result.scalars().all()
    return [AttendanceOut.model_validate(r) for r in records]


@router.get(
    "/worker/{worker_id}",
    response_model=list[AttendanceOut],
    summary="View worker attendance (Manager)",
    description="Managers can view attendance records for workers in their department.",
    operation_id="getWorkerAttendance",
)
async def worker_attendance(
    worker_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
    from_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    try:
        wid = uuid.UUID(worker_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid worker ID")
    q = select(AttendanceRecord).where(AttendanceRecord.user_id == wid)
    if from_date:
        q = q.where(AttendanceRecord.date >= from_date)
    if to_date:
        q = q.where(AttendanceRecord.date <= to_date)
    q = q.order_by(AttendanceRecord.date.desc()).limit(90)
    result = await db.execute(q)
    records = result.scalars().all()
    return [AttendanceOut.model_validate(r) for r in records]
