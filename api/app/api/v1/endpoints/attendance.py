from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff
from app.db.database import get_db
from app.models.models import AttendanceRecord, User, WorkerProfile
from app.schemas.attendance import (
    AttendanceOut,
    AttendanceStatusOut,
    ClockInRequest,
    ClockOutRequest,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.post(
    "/clock-in",
    response_model=AttendanceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Clock in",
    description="Record clock-in for today. One active clock-in per user per day. **Access:** fieldManager, fieldAssistant, or admin (Bearer required).",
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
    summary="Clock out",
    description="Record clock-out for the active clock-in. **Access:** fieldManager, fieldAssistant, or admin (Bearer required).",
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active clock-in found")

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
    summary="Attendance status",
    description="Current clock-in status and today's record for the authenticated user. **Access:** fieldManager, fieldAssistant, or admin (Bearer required).",
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
