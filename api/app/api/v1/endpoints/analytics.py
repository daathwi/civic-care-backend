import uuid
from datetime import date, datetime, timedelta, timezone
import asyncio
import smtplib
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, and_, cast, Date, String
from sqlalchemy.orm import selectinload, aliased

from app.api.deps import require_admin, require_manager
from app.core.config import settings
from app.db.database import get_db
from app.services.analytics_pdf import build_performance_report_pdf
from app.services.eps_service import get_ward_maxima, calculate_eps
from app.services.cis_cron import compute_cis_snapshots
from app.services.cis_service import (
    calculate_user_cis,
    fetch_citizen_cis_leaderboard,
    fetch_latest_cis_snapshot,
    format_datetime_display_ist,
    format_iso_ist,
    get_cis_scheduler_state,
)
from app.models.models import (
    Grievance,
    GrievanceCategory,
    Department,
    Ward,
    Zone,
    PoliticalParty,
    Assignment,
    User,
    WorkerProfile,
    GrievanceResolutionRating,
    AttendanceRecord,
)
from typing import Annotated, List, Dict, Any

router = APIRouter(prefix="/analytics", tags=["analytics"])
SLA_HOURS = 48


def _compute_department_dpi(
    t: int, r: int, p: int, s_count: int, rc: int, sum_ri: int, e: int
) -> float:
    """Compute department DPI: 30% Res + 25% SLA + 20% Caseload + 15% Quality + 10% Escalation."""
    if t == 0:
        return 70.0
    resolution_rate = r / t
    pending_score = 1 - (p / t)
    sla_rate = s_count / r if r > 0 else 1.0
    recurrence_score = 1 - (sum_ri / r) if r > 0 else (1 if sum_ri == 0 else 0)
    escalation_score = 1 - (e / t)
    return (
        0.30 * resolution_rate
        + 0.25 * sla_rate
        + 0.20 * pending_score
        + 0.15 * max(0, recurrence_score)
        + 0.10 * escalation_score
    ) * 100


def _role_str(u: User) -> str:
    r = getattr(u, "role", None)
    if r is None:
        return ""
    return getattr(r, "value", r) if hasattr(r, "value") else str(r)


@router.get(
    "/departments",
    summary="See how departments are doing",
    description="Get a breakdown of performance for each department. Filter by ward_id, zone_id, or omit for overall (city-wide) metrics.",
    operation_id="fetchDepartmentPerformanceMetrics",
)
async def get_department_analytics(
    db: AsyncSession = Depends(get_db),
    ward_id: uuid.UUID | None = Query(None, description="Filter by ward UUID. Returns department performance for that ward only."),
    zone_id: uuid.UUID | None = Query(None, description="Filter by zone UUID. Returns department performance for all wards in that zone."),
):
    # SLA threshold (48 hours)
    SLA_HOURS = 48
    
    # Base query: Department -> Category -> Grievance
    query = (
        select(
            Department.id,
            Department.name,
            Department.sdg,
            Department.description,
            func.count(Grievance.id).label("total"),
            func.sum(case((Grievance.status == 'resolved', 1), else_=0)).label("resolved"),
            func.sum(case((and_(Grievance.id != None, Grievance.status != 'resolved'), 1), else_=0)).label("pending"),
            func.sum(case((and_(Grievance.status == 'resolved', Grievance.updated_at - Grievance.created_at > timedelta(hours=SLA_HOURS)), 1), else_=0)).label("sla_breaches_resolved"),
            func.sum(case((and_(Grievance.status != 'resolved', func.now() - Grievance.created_at > timedelta(hours=SLA_HOURS)), 1), else_=0)).label("sla_breaches_pending"),
            func.sum(case((Grievance.reopen_count > 0, 1), else_=0)).label("repeat_complaints"),
            func.sum(func.coalesce(Grievance.reopen_count, 0)).label("total_repeat_count"),
            func.sum(case((Grievance.status == 'escalated', 1), else_=0)).label("escalated")
        )
        .select_from(Department)
        .join(GrievanceCategory, Department.id == GrievanceCategory.dept_id, isouter=True)
        .join(Grievance, GrievanceCategory.id == Grievance.category_id, isouter=True)
    )

    # Apply ward or zone filter (overall when both are None)
    if ward_id is not None:
        query = query.where(Grievance.ward_id == ward_id)
    elif zone_id is not None:
        query = query.join(Ward, Grievance.ward_id == Ward.id).where(Ward.zone_id == zone_id)

    query = query.group_by(Department.id, Department.name, Department.sdg, Department.description)
    
    result = await db.execute(query)
    rows = result.all()
    
    analytics = []
    for row in rows:
        t = row.total
        r = row.resolved
        p = row.pending
        # Breaches (Bad)
        bh = row.sla_breaches_resolved
        bp = row.sla_breaches_pending
        
        # S is now exclusively "Resolved within SLA"
        s_count = r - bh
        
        rc = row.repeat_complaints
        sum_ri = row.total_repeat_count
        e = row.escalated
        
        # Operational Efficiency
        resolution_rate = r / t if t > 0 else 0
        pending_score = 1 - (p / t) if t > 0 else 1
        
        # Service Velocity (SLA Adherence)
        # Using S/R to measure timeliness of completed work
        sla_rate = s_count / r if r > 0 else 1.0
        
        # Quality & Escalation
        recurrence_rate = rc / t if t > 0 else 0
        average_recurrence = sum_ri / rc if rc > 0 else 0
        recurrence_score = 1 - (sum_ri / r) if r > 0 else (1 if sum_ri == 0 else 0)
        
        # Escalation Mitigation (1 - E/T)
        escalation_rate = e / t if t > 0 else 0
        escalation_score = 1 - escalation_rate
        
        # Unified DPI: 30% Res + 25% SLA + 20% Caseload + 15% Quality + 10% Escalation
        if t == 0:
            dpi = 70.0  # Baseline for zero inflow
        else:
            dpi = (
                0.30 * resolution_rate +
                0.25 * sla_rate +
                0.20 * pending_score +
                0.15 * max(0, recurrence_score) +
                0.10 * escalation_score
            ) * 100
        
        # Performance Classification
        performance = "Excellent"
        if dpi < 60: performance = "Critical"
        elif dpi < 70: performance = "Poor"
        elif dpi < 80: performance = "Average"
        elif dpi < 90: performance = "Good"
        
        analytics.append({
            "id": str(row.id),
            "name": row.name,
            "sdg": row.sdg,
            "description": row.description,
            "metrics": {
                "total": t,
                "resolved": r,
                "pending": p,
                "sla_resolved": s_count,
                "repeat_complaints": rc,
                "total_repeat_count": int(sum_ri),
                "escalated": e
            },
            "scores": {
                "resolution_rate": round(resolution_rate, 4),
                "pending_score": round(pending_score, 4),
                "sla_rate": round(sla_rate, 4),
                "recurrence_rate": round(recurrence_rate, 4),
                "average_recurrence": round(average_recurrence, 2),
                "recurrence_score": round(max(0, recurrence_score), 4),
                "escalation_rate": round(escalation_rate, 4),
                "escalation_score": round(escalation_score, 4),
                "dpi": round(dpi, 2)
            },
            "performance": performance
        })
        
    # Sort by DPI descending
    analytics.sort(key=lambda x: x["scores"]["dpi"], reverse=True)
    
    return analytics


@router.get(
    "/departments/{department_id}/detail",
    summary="Department detail analytics",
    description="Time series and heatmap data for a department's performance. Use month/year to select a specific month.",
    operation_id="fetchDepartmentDetailAnalytics",
)
async def get_department_detail_analytics(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ward_id: uuid.UUID | None = Query(None, description="Filter by ward."),
    zone_id: uuid.UUID | None = Query(None, description="Filter by zone."),
    month: int | None = Query(None, ge=1, le=12, description="Month (1-12). Required with year."),
    year: int | None = Query(None, ge=2020, le=2030, description="Year. Required with month."),
):
    """Returns time_series (daily aggregates for the month) and heatmap (day-of-week x week within month)."""
    dept = (await db.execute(select(Department).where(Department.id == department_id))).scalar_one_or_none()
    if not dept:
        raise HTTPException(404, "Department not found")

    today = date.today()
    sel_month = month if month is not None else today.month
    sel_year = year if year is not None else today.year
    start_date = date(sel_year, sel_month, 1)
    # Last day of month
    if sel_month == 12:
        end_date = date(sel_year, 12, 31)
    else:
        end_date = date(sel_year, sel_month + 1, 1) - timedelta(days=1)

    # Base: grievances for this department in the selected month
    q = (
        select(
            cast(Grievance.created_at, Date).label("d"),
            func.count(Grievance.id).label("total"),
            func.sum(case((Grievance.status == "resolved", 1), else_=0)).label("resolved"),
            func.sum(case((and_(Grievance.id != None, Grievance.status != "resolved"), 1), else_=0)).label("pending"),
            func.sum(case((Grievance.status == "escalated", 1), else_=0)).label("escalated"),
        )
        .select_from(Grievance)
        .join(GrievanceCategory, Grievance.category_id == GrievanceCategory.id)
        .where(
            GrievanceCategory.dept_id == department_id,
            Grievance.created_at >= datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc),
            Grievance.created_at < datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc)
            + timedelta(days=1),
        )
    )
    if ward_id is not None:
        q = q.where(Grievance.ward_id == ward_id)
    elif zone_id is not None:
        q = q.join(Ward, Grievance.ward_id == Ward.id).where(Ward.zone_id == zone_id)
    q = q.group_by(cast(Grievance.created_at, Date))

    result = await db.execute(q)
    rows = result.all()

    def _int(v):
        return int(v) if v is not None else 0

    # Build daily map
    by_date = {}
    for r in rows:
        d_val = r.d
        if hasattr(d_val, "date"):
            key = d_val.date().isoformat() if hasattr(d_val, "date") else str(d_val)
        else:
            key = d_val.isoformat() if hasattr(d_val, "isoformat") else str(d_val)
        by_date[key] = r

    # Time series: one entry per day in the month (month-wise)
    time_series = []
    days_in_month = (end_date - start_date).days + 1
    for i in range(days_in_month):
        d = start_date + timedelta(days=i)
        key = d.isoformat()
        r = by_date.get(key)
        time_series.append({
            "date": key,
            "day": d.day,
            "total": _int(r.total) if r else 0,
            "resolved": _int(r.resolved) if r else 0,
            "pending": _int(r.pending) if r else 0,
            "escalated": _int(r.escalated) if r else 0,
        })

    # Heatmap: month-wise. Rows = weeks (0-5), cols = Mon-Sun. week = (day-1 + first_weekday)//7.
    heatmap = []
    first_weekday = start_date.weekday()  # 0=Mon, 6=Sun
    for d in [start_date + timedelta(days=i) for i in range(days_in_month)]:
        day_num = d.day
        week = (day_num - 1 + first_weekday) // 7
        dow = d.weekday()
        key = d.isoformat()
        r = by_date.get(key)
        count = _int(r.total) if r else 0
        heatmap.append({
            "week": week,
            "day_of_week": dow,
            "date": key,
            "day": day_num,
            "count": count,
        })

    return {
        "department_id": str(department_id),
        "department_name": dept.name,
        "month": sel_month,
        "year": sel_year,
        "time_series": time_series,
        "heatmap": heatmap,
    }


# ── Worker Analytics ────────────────────────────────────────────────────────


@router.get(
    "/workers",
    summary="Worker performance analytics",
    description="Aggregated metrics for all workers. Managers see only their department; admins see all.",
    operation_id="fetchWorkerAnalytics",
)
async def get_worker_analytics(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
    department_id: uuid.UUID | None = Query(None, description="Filter by department. Manager's dept used if omitted."),
    ward_id: uuid.UUID | None = Query(None, description="Filter by ward UUID."),
    from_date: date | None = Query(None, description="Start date (YYYY-MM-DD) for period metrics."),
    to_date: date | None = Query(None, description="End date (YYYY-MM-DD) for period metrics."),
):
    """Returns list of workers with performance metrics: tasks, SLA, ratings, attendance."""
    wp = user.worker_profile
    effective_dept = department_id
    # Only use manager's department as fallback when not admin; admin with "All departments" gets all workers
    if effective_dept is None and _role_str(user) != "admin" and wp and wp.department_id:
        effective_dept = wp.department_id
    if _role_str(user) != "admin" and effective_dept is None:
        return []

    # Base: workers (field assistants + managers) with profiles
    worker_query = (
        select(User)
        .join(WorkerProfile, WorkerProfile.user_id == User.id)
        .options(
            selectinload(User.worker_profile).selectinload(WorkerProfile.department),
            selectinload(User.worker_profile).selectinload(WorkerProfile.ward),
        )
        .where(User.role.in_(["fieldManager", "fieldAssistant"]))
    )
    if effective_dept:
        worker_query = worker_query.where(WorkerProfile.department_id == effective_dept)
    if ward_id:
        worker_query = worker_query.where(WorkerProfile.ward_id == ward_id)

    worker_result = await db.execute(worker_query)
    workers = worker_result.scalars().unique().all()

    period_start = from_date
    period_end = to_date
    if period_start is None:
        period_start = date.today() - timedelta(days=30)
    if period_end is None:
        period_end = date.today()

    period_start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc)
    period_end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=timezone.utc) + timedelta(days=1)

    out = []
    for w in workers:
        wid = w.id
        wp = w.worker_profile
        if not wp:
            continue

        # Assignments completed in period (worker was resolver)
        sla_seconds = SLA_HOURS * 3600
        assign_q = (
            select(
                func.count(Assignment.id).label("resolved_count"),
                func.sum(
                    case(
                        (
                            and_(
                                Assignment.completed_at.isnot(None),
                                func.coalesce(
                                    func.extract("epoch", Assignment.completed_at - Assignment.assigned_at),
                                    0,
                                )
                                <= sla_seconds,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("sla_ok"),
                func.sum(case((Assignment.completed_at.isnot(None), 1), else_=0)).label("total_completed"),
            )
        ).select_from(Assignment).where(
            Assignment.assigned_to_id == wid,
            Assignment.completed_at.isnot(None),
            Assignment.completed_at >= period_start_dt,
            Assignment.completed_at < period_end_dt,
        )
        assign_row = (await db.execute(assign_q)).one()
        period_resolved = assign_row.resolved_count or 0
        period_sla_ok = assign_row.sla_ok or 0
        period_total = assign_row.total_completed or 0
        sla_rate = period_sla_ok / period_total if period_total > 0 else 1.0

        # Reopened grievances (worker was resolver, grievance was reopened)
        reopen_q = (
            select(func.count(Grievance.id))
            .select_from(Grievance)
            .join(Assignment, and_(Assignment.grievance_id == Grievance.id, Assignment.assigned_to_id == wid))
            .where(
                Grievance.reopen_count > 0,
                Grievance.updated_at >= period_start_dt,
                Grievance.updated_at < period_end_dt,
            )
        )
        reopen_count = (await db.execute(reopen_q)).scalar() or 0

        # Escalated (worker was assigned, grievance escalated)
        esc_q = (
            select(func.count(Grievance.id))
            .select_from(Grievance)
            .join(Assignment, and_(Assignment.grievance_id == Grievance.id, Assignment.assigned_to_id == wid))
            .where(
                Grievance.status == "escalated",
                Grievance.updated_at >= period_start_dt,
                Grievance.updated_at < period_end_dt,
            )
        )
        escalated_count = (await db.execute(esc_q)).scalar() or 0

        # Avg resolution time (hours) in period
        avg_time_q = (
            select(
                func.avg(
                    func.extract("epoch", Assignment.completed_at - Assignment.assigned_at) / 3600.0
                ).label("avg_hours"),
            )
        ).select_from(Assignment).where(
            Assignment.assigned_to_id == wid,
            Assignment.completed_at.isnot(None),
            Assignment.completed_at >= period_start_dt,
            Assignment.completed_at < period_end_dt,
        )
        avg_hours_row = (await db.execute(avg_time_q)).one()
        avg_resolution_hours = float(avg_hours_row.avg_hours) if avg_hours_row.avg_hours else None

        # Ratings in period
        rating_q = (
            select(
                func.avg(GrievanceResolutionRating.rating).label("avg_rating"),
                func.count(GrievanceResolutionRating.id).label("count"),
            )
        ).select_from(GrievanceResolutionRating).where(
            GrievanceResolutionRating.worker_id == wid,
            GrievanceResolutionRating.created_at >= period_start_dt,
            GrievanceResolutionRating.created_at < period_end_dt,
        )
        rating_row = (await db.execute(rating_q)).one()
        period_avg_rating = float(rating_row.avg_rating) if rating_row.avg_rating else None
        period_ratings_count = rating_row.count or 0

        # Attendance in period
        att_q = (
            select(
                func.count(AttendanceRecord.id).label("days_present"),
                func.avg(AttendanceRecord.total_duration_seconds).label("avg_seconds"),
            )
        ).select_from(AttendanceRecord).where(
            AttendanceRecord.user_id == wid,
            AttendanceRecord.date >= period_start,
            AttendanceRecord.date <= period_end,
            AttendanceRecord.total_duration_seconds.isnot(None),
        )
        att_row = (await db.execute(att_q)).one()
        days_present = att_row.days_present or 0
        avg_seconds = att_row.avg_seconds
        avg_hours_per_day = float(avg_seconds) / 3600.0 if avg_seconds else None
        period_days = (period_end - period_start).days + 1
        attendance_rate = days_present / period_days if period_days > 0 else 0

        out.append({
            "id": str(wid),
            "name": w.name,
            "phone": w.phone if w.phone else None,
            "department_id": str(wp.department_id) if wp.department_id else None,
            "department_name": wp.department.name if wp.department else None,
            "ward_id": str(wp.ward_id) if wp.ward_id else None,
            "ward_name": wp.ward.name if wp.ward else None,
            "designation": wp.designation_title or "",
            "status": wp.current_status or "offDuty",
            "metrics": {
                "tasks_completed": wp.tasks_completed or 0,
                "tasks_active": wp.tasks_active or 0,
                "rating": float(wp.rating) if wp.rating else None,
                "ratings_count": wp.ratings_count or 0,
                "period_resolved": period_resolved,
                "period_sla_ok": int(period_sla_ok),
                "sla_rate": round(sla_rate, 4),
                "reopen_count": reopen_count,
                "escalated_count": escalated_count,
                "avg_resolution_hours": round(avg_resolution_hours, 2) if avg_resolution_hours is not None else None,
                "period_avg_rating": round(period_avg_rating, 2) if period_avg_rating is not None else None,
                "period_ratings_count": period_ratings_count,
                "days_present": days_present,
                "attendance_rate": round(attendance_rate, 4),
                "avg_hours_per_day": round(avg_hours_per_day, 2) if avg_hours_per_day is not None else None,
            },
            "period": {"from": period_start.isoformat(), "to": period_end.isoformat()},
        })
    return out


@router.get(
    "/workers/{worker_id}",
    summary="Single worker analytics",
    description="Detailed analytics for one worker: time series, attendance, ratings trend.",
    operation_id="fetchWorkerDetailAnalytics",
)
async def get_worker_detail_analytics(
    worker_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
    from_date: date | None = Query(None, description="Start date (YYYY-MM-DD)."),
    to_date: date | None = Query(None, description="End date (YYYY-MM-DD)."),
):
    wp = user.worker_profile
    if _role_str(user) != "admin" and (not wp or not wp.department_id):
        raise HTTPException(403, "Manager must have department")
    worker = (
        await db.execute(
            select(User)
            .options(
                selectinload(User.worker_profile).selectinload(WorkerProfile.department),
                selectinload(User.worker_profile).selectinload(WorkerProfile.ward),
            )
            .where(User.id == worker_id)
        )
    )
    worker = worker.scalar_one_or_none()
    if not worker or not worker.worker_profile:
        raise HTTPException(404, "Worker not found")
    if _role_str(user) != "admin" and worker.worker_profile.department_id != wp.department_id:
        raise HTTPException(403, "Worker not in your department")

    period_start = from_date or (date.today() - timedelta(days=30))
    period_end = to_date or date.today()
    period_start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc)
    period_end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=timezone.utc) + timedelta(days=1)

    # Daily resolution count
    daily_q = (
        select(
            cast(Assignment.completed_at, Date).label("d"),
            func.count(Assignment.id).label("cnt"),
        )
        .select_from(Assignment)
        .where(
            Assignment.assigned_to_id == worker_id,
            Assignment.completed_at.isnot(None),
            Assignment.completed_at >= period_start_dt,
            Assignment.completed_at < period_end_dt,
        )
    ).group_by(cast(Assignment.completed_at, Date))
    daily_rows = (await db.execute(daily_q)).all()
    by_date = {str(r.d): r.cnt for r in daily_rows}

    time_series = []
    d = period_start
    while d <= period_end:
        key = d.isoformat()
        time_series.append({"date": key, "resolved": by_date.get(key, 0)})
        d += timedelta(days=1)

    # Attendance records
    att_q = (
        select(AttendanceRecord)
        .where(
            AttendanceRecord.user_id == worker_id,
            AttendanceRecord.date >= period_start,
            AttendanceRecord.date <= period_end,
        )
        .order_by(AttendanceRecord.date.desc())
    )
    att_records = (await db.execute(att_q)).scalars().all()
    attendance = [
        {
            "date": r.date.isoformat(),
            "clock_in": r.clock_in_time.isoformat() if r.clock_in_time else None,
            "clock_out": r.clock_out_time.isoformat() if r.clock_out_time else None,
            "duration_hours": round(r.total_duration_seconds / 3600.0, 2) if r.total_duration_seconds else None,
        }
        for r in att_records
    ]

    # Ratings over time
    rating_q = (
        select(
            cast(GrievanceResolutionRating.created_at, Date).label("d"),
            func.avg(GrievanceResolutionRating.rating).label("avg_r"),
            func.count(GrievanceResolutionRating.id).label("cnt"),
        )
        .select_from(GrievanceResolutionRating)
        .where(
            GrievanceResolutionRating.worker_id == worker_id,
            GrievanceResolutionRating.created_at >= period_start_dt,
            GrievanceResolutionRating.created_at < period_end_dt,
        )
    ).group_by(cast(GrievanceResolutionRating.created_at, Date))
    rating_rows = (await db.execute(rating_q)).all()
    rating_by_date = {str(r.d): {"avg": float(r.avg_r), "count": r.cnt} for r in rating_rows}

    rating_series = []
    d = period_start
    while d <= period_end:
        key = d.isoformat()
        r = rating_by_date.get(key, {"avg": None, "count": 0})
        rating_series.append({"date": key, "avg_rating": r["avg"], "count": r["count"]})
        d += timedelta(days=1)

    period_ratings_count = sum(r.get("count", 0) or 0 for r in rating_by_date.values())
    period_avg_rating = None
    if period_ratings_count > 0:
        weighted = sum((r.get("avg") or 0) * (r.get("count") or 0) for r in rating_by_date.values())
        period_avg_rating = weighted / period_ratings_count

    # Period-level metrics (matching list view)
    sla_seconds = SLA_HOURS * 3600
    assign_q = (
        select(
            func.count(Assignment.id).label("resolved_count"),
            func.sum(
                case(
                    (
                        and_(
                            Assignment.completed_at.isnot(None),
                            func.coalesce(
                                func.extract("epoch", Assignment.completed_at - Assignment.assigned_at),
                                0,
                            )
                            <= sla_seconds,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("sla_ok"),
            func.sum(case((Assignment.completed_at.isnot(None), 1), else_=0)).label("total_completed"),
        )
    ).select_from(Assignment).where(
        Assignment.assigned_to_id == worker_id,
        Assignment.completed_at.isnot(None),
        Assignment.completed_at >= period_start_dt,
        Assignment.completed_at < period_end_dt,
    )
    assign_row = (await db.execute(assign_q)).one()
    period_resolved = assign_row.resolved_count or 0
    period_sla_ok = assign_row.sla_ok or 0
    period_total = assign_row.total_completed or 0
    sla_rate = period_sla_ok / period_total if period_total > 0 else 1.0

    reopen_q = (
        select(func.count(Grievance.id))
        .select_from(Grievance)
        .join(Assignment, and_(Assignment.grievance_id == Grievance.id, Assignment.assigned_to_id == worker_id))
        .where(
            Grievance.reopen_count > 0,
            Grievance.updated_at >= period_start_dt,
            Grievance.updated_at < period_end_dt,
        )
    )
    reopen_count = (await db.execute(reopen_q)).scalar() or 0

    esc_q = (
        select(func.count(Grievance.id))
        .select_from(Grievance)
        .join(Assignment, and_(Assignment.grievance_id == Grievance.id, Assignment.assigned_to_id == worker_id))
        .where(
            Grievance.status == "escalated",
            Grievance.updated_at >= period_start_dt,
            Grievance.updated_at < period_end_dt,
        )
    )
    escalated_count = (await db.execute(esc_q)).scalar() or 0

    avg_time_q = (
        select(
            func.avg(
                func.extract("epoch", Assignment.completed_at - Assignment.assigned_at) / 3600.0
            ).label("avg_hours"),
        )
    ).select_from(Assignment).where(
        Assignment.assigned_to_id == worker_id,
        Assignment.completed_at.isnot(None),
        Assignment.completed_at >= period_start_dt,
        Assignment.completed_at < period_end_dt,
    )
    avg_hours_row = (await db.execute(avg_time_q)).one()
    avg_resolution_hours = float(avg_hours_row.avg_hours) if avg_hours_row.avg_hours else None

    period_days = (period_end - period_start).days + 1
    days_present = len(attendance)
    attendance_rate = days_present / period_days if period_days > 0 else 0

    wp = worker.worker_profile
    return {
        "worker_id": str(worker_id),
        "name": worker.name,
        "phone": worker.phone if worker.phone else None,
        "department_name": wp.department.name if wp.department else None,
        "ward_name": wp.ward.name if wp.ward else None,
        "designation": wp.designation_title or "",
        "status": wp.current_status or "offDuty",
        "metrics": {
            "tasks_completed": wp.tasks_completed or 0,
            "tasks_active": wp.tasks_active or 0,
            "rating": float(wp.rating) if wp.rating else None,
            "ratings_count": wp.ratings_count or 0,
            "period_resolved": period_resolved,
            "period_sla_ok": int(period_sla_ok),
            "sla_rate": round(sla_rate, 4),
            "reopen_count": reopen_count,
            "escalated_count": escalated_count,
            "avg_resolution_hours": round(avg_resolution_hours, 2) if avg_resolution_hours is not None else None,
            "period_avg_rating": round(period_avg_rating, 2) if period_avg_rating is not None else None,
            "period_ratings_count": period_ratings_count,
            "days_present": days_present,
            "attendance_rate": round(attendance_rate, 4),
        },
        "period": {"from": period_start.isoformat(), "to": period_end.isoformat(), "days": period_days},
        "time_series": time_series,
        "attendance": attendance,
        "rating_series": rating_series,
    }


@router.get(
    "/wards",
    summary="Check ward activity",
    description="See analytics and reported issues for individual wards. Ward Performance Index = Σ(Department Scores) / Number of Departments.",
    operation_id="fetchWardActivityOverview",
)
async def get_ward_analytics(
    db: AsyncSession = Depends(get_db),
    zone_id: uuid.UUID | None = Query(None, description="Filter by zone UUID. Returns ward performance for that zone only."),
):
    """Returns list of wards. Ward Performance Index = avg of department DPIs for departments active in that ward."""
    # Per-ward, per-department metrics (grievances must have category to attribute to department)
    dept_ward_query = (
        select(
            Ward.id,
            Ward.name,
            Ward.number,
            Ward.zone_id,
            Department.id.label("dept_id"),
            Department.name.label("dept_name"),
            func.count(Grievance.id).label("total"),
            func.sum(case((Grievance.status == "resolved", 1), else_=0)).label("resolved"),
            func.sum(case((and_(Grievance.id != None, Grievance.status != "resolved"), 1), else_=0)).label("pending"),
            func.sum(case((and_(Grievance.status == "resolved", Grievance.updated_at - Grievance.created_at > timedelta(hours=SLA_HOURS)), 1), else_=0)).label("sla_breaches_resolved"),
            func.sum(case((Grievance.reopen_count > 0, 1), else_=0)).label("repeat_complaints"),
            func.sum(func.coalesce(Grievance.reopen_count, 0)).label("total_repeat_count"),
            func.sum(case((Grievance.status == "escalated", 1), else_=0)).label("escalated"),
        )
        .select_from(Ward)
        .join(Grievance, and_(Grievance.ward_id == Ward.id, Grievance.category_id.isnot(None)))
        .join(GrievanceCategory, Grievance.category_id == GrievanceCategory.id)
        .join(Department, GrievanceCategory.dept_id == Department.id)
    )
    if zone_id is not None:
        dept_ward_query = dept_ward_query.where(Ward.zone_id == zone_id)
    dept_ward_query = dept_ward_query.group_by(Ward.id, Ward.name, Ward.number, Ward.zone_id, Department.id, Department.name)

    dept_ward_result = await db.execute(dept_ward_query)
    dept_ward_rows = dept_ward_result.all()

    # Ward-level totals (all grievances, including those without category)
    ward_totals_query = (
        select(
            Ward.id,
            Ward.name,
            Ward.number,
            Ward.zone_id,
            Ward.representative_name,
            Ward.representative_phone,
            PoliticalParty.short_code.label("party_short_code"),
            func.count(Grievance.id).label("total"),
            func.sum(case((Grievance.status == "resolved", 1), else_=0)).label("resolved"),
            func.sum(case((and_(Grievance.id != None, Grievance.status != "resolved"), 1), else_=0)).label("pending"),
            func.sum(case((and_(Grievance.status == "resolved", Grievance.updated_at - Grievance.created_at <= timedelta(hours=SLA_HOURS)), 1), else_=0)).label("sla_resolved"),
            func.sum(case((Grievance.status == "escalated", 1), else_=0)).label("escalated"),
        )
        .select_from(Ward)
        .outerjoin(PoliticalParty, Ward.party_id == PoliticalParty.id)
        .join(Grievance, Grievance.ward_id == Ward.id, isouter=True)
    )
    if zone_id is not None:
        ward_totals_query = ward_totals_query.where(Ward.zone_id == zone_id)
    ward_totals_query = ward_totals_query.group_by(Ward.id, Ward.name, Ward.number, Ward.zone_id, Ward.representative_name, Ward.representative_phone, PoliticalParty.short_code)

    ward_totals_result = await db.execute(ward_totals_query)
    ward_totals = {r.id: r for r in ward_totals_result.all()}

    # Compute department DPI per (ward, department), then aggregate per ward
    ward_dept_scores: Dict[uuid.UUID, List[float]] = {}
    for row in dept_ward_rows:
        t = row.total or 0
        r = row.resolved or 0
        p = row.pending or 0
        bh = row.sla_breaches_resolved or 0
        s_count = r - bh
        rc = row.repeat_complaints or 0
        sum_ri = row.total_repeat_count or 0
        e = row.escalated or 0

        dept_dpi = _compute_department_dpi(t, r, p, s_count, rc, sum_ri, e)
        ward_id = row.id
        if ward_id not in ward_dept_scores:
            ward_dept_scores[ward_id] = []
        ward_dept_scores[ward_id].append(dept_dpi)

    # Get zone names
    ward_ids = list(ward_totals.keys())
    zone_ids = {ward_totals[w].zone_id for w in ward_ids if ward_totals[w].zone_id}
    zone_names = {}
    if zone_ids:
        zone_res = await db.execute(select(Zone.id, Zone.name).where(Zone.id.in_(zone_ids)))
        zone_names = {str(r.id): r.name for r in zone_res.all()}

    analytics = []
    for ward_id, tot in ward_totals.items():
        t = tot.total or 0
        r = tot.resolved or 0
        p = tot.pending or 0
        s_count = tot.sla_resolved or 0
        e = tot.escalated or 0

        # Ward Performance Index = Σ(Department Scores) / Number of Departments
        dept_scores = ward_dept_scores.get(ward_id, [])
        if dept_scores:
            dpi = sum(dept_scores) / len(dept_scores)
        else:
            dpi = 70.0  # Baseline when no departments have activity in this ward

        resolution_rate = r / t if t > 0 else 0
        sla_rate = s_count / r if r > 0 else 1.0
        pending_score = 1 - (p / t) if t > 0 else 1
        escalation_score = 1 - (e / t) if t > 0 else 1

        performance = "Excellent"
        if dpi < 60:
            performance = "Critical"
        elif dpi < 70:
            performance = "Poor"
        elif dpi < 80:
            performance = "Average"
        elif dpi < 90:
            performance = "Good"

        rep_phone = tot.representative_phone if hasattr(tot, "representative_phone") and tot.representative_phone else []
        party_short_code = getattr(tot, "party_short_code", None) or None
        analytics.append({
            "id": str(ward_id),
            "name": tot.name,
            "number": tot.number,
            "party_short_code": party_short_code,
            "representative_name": tot.representative_name if hasattr(tot, "representative_name") else None,
            "representative_phone": rep_phone if isinstance(rep_phone, list) else ([rep_phone] if rep_phone else []),
            "zone_id": str(tot.zone_id) if tot.zone_id else None,
            "zone_name": zone_names.get(str(tot.zone_id), "–") if tot.zone_id else "–",
            "metrics": {
                "total": t,
                "resolved": r,
                "pending": p,
                "sla_resolved": s_count,
                "escalated": e,
            },
            "scores": {
                "resolution_rate": round(resolution_rate, 4),
                "sla_rate": round(sla_rate, 4),
                "pending_score": round(pending_score, 4),
                "escalation_score": round(escalation_score, 4),
                "wpi": round(dpi, 2),
            },
            "performance": performance,
        })

    analytics.sort(key=lambda x: x["scores"]["wpi"], reverse=True)
    return analytics


@router.get(
    "/parties/control",
    summary="Political party control analytics",
    description="Party-wise ward counts, grievance metrics, and performance for map visualization and area-of-control analysis.",
    operation_id="fetchPartyControlAnalytics",
)
async def get_party_control_analytics(db: AsyncSession = Depends(get_db)):
    """Returns party control stats (ward count, %), grievance metrics, and avg WPI per party."""
    # Ward counts per party
    ward_party_query = (
        select(
            PoliticalParty.id,
            PoliticalParty.name,
            PoliticalParty.short_code,
            PoliticalParty.color,
            func.count(Ward.id).label("ward_count"),
        )
        .select_from(PoliticalParty)
        .join(Ward, Ward.party_id == PoliticalParty.id)
        .group_by(PoliticalParty.id, PoliticalParty.name, PoliticalParty.short_code, PoliticalParty.color)
    )
    result = await db.execute(ward_party_query)
    party_rows = result.all()

    # Total ward count
    total_result = await db.execute(select(func.count(Ward.id)).select_from(Ward))
    total_wards = total_result.scalar() or 0

    # Ward list with party info for map styling
    wards_result = await db.execute(
        select(Ward.id, Ward.name, Ward.number, Ward.party_id, PoliticalParty.color, PoliticalParty.short_code)
        .select_from(Ward)
        .outerjoin(PoliticalParty, Ward.party_id == PoliticalParty.id)
    )
    ward_rows = wards_result.all()

    # Grievance metrics per party (party -> ward -> grievance)
    grievance_query = (
        select(
            Ward.party_id,
            func.count(Grievance.id).label("total"),
            func.sum(case((Grievance.status == "resolved", 1), else_=0)).label("resolved"),
            func.sum(case((and_(Grievance.id != None, Grievance.status != "resolved"), 1), else_=0)).label("pending"),
            func.sum(case((Grievance.status == "escalated", 1), else_=0)).label("escalated"),
            func.sum(case((and_(Grievance.status == "resolved", Grievance.updated_at - Grievance.created_at <= timedelta(hours=SLA_HOURS)), 1), else_=0)).label("sla_resolved"),
        )
        .select_from(Ward)
        .join(Grievance, Grievance.ward_id == Ward.id)
        .where(Ward.party_id.isnot(None))
        .group_by(Ward.party_id)
    )
    grievance_result = await db.execute(grievance_query)
    grievance_by_party = {str(r.party_id): r for r in grievance_result.all()}

    # Grievance metrics for unassigned wards (party_id is NULL)
    unassigned_griev_query = (
        select(
            func.count(Grievance.id).label("total"),
            func.sum(case((Grievance.status == "resolved", 1), else_=0)).label("resolved"),
            func.sum(case((and_(Grievance.id != None, Grievance.status != "resolved"), 1), else_=0)).label("pending"),
            func.sum(case((Grievance.status == "escalated", 1), else_=0)).label("escalated"),
            func.sum(case((and_(Grievance.status == "resolved", Grievance.updated_at - Grievance.created_at <= timedelta(hours=SLA_HOURS)), 1), else_=0)).label("sla_resolved"),
        )
        .select_from(Ward)
        .join(Grievance, Grievance.ward_id == Ward.id)
        .where(Ward.party_id.is_(None))
    )
    unassigned_griev = (await db.execute(unassigned_griev_query)).first()

    # Ward analytics for avg WPI per party
    ward_analytics = await get_ward_analytics(db, zone_id=None)
    ward_to_party = {str(r.id): (str(r.party_id) if r.party_id else None) for r in ward_rows}
    wpi_by_party: Dict[str, List[float]] = {}
    for w in ward_analytics:
        wid = w.get("id")
        pid = ward_to_party.get(wid) if wid else None
        if pid not in wpi_by_party:
            wpi_by_party[pid] = []
        wpi = w.get("scores", {}).get("wpi")
        if wpi is not None:
            wpi_by_party[pid].append(wpi)

    def _metrics_for_party(pid: str | None):
        g = grievance_by_party.get(pid) if pid else unassigned_griev
        if g is None:
            return {"total": 0, "resolved": 0, "pending": 0, "escalated": 0, "sla_resolved": 0, "resolution_pct": 0, "sla_pct": 0}
        t = g.total or 0
        r = g.resolved or 0
        s = g.sla_resolved or 0
        resolution_pct = round((r / t) * 100, 1) if t > 0 else 0
        sla_pct = round((s / r) * 100, 1) if r > 0 else 0
        return {
            "total": t, "resolved": r, "pending": g.pending or 0, "escalated": g.escalated or 0, "sla_resolved": s,
            "resolution_pct": resolution_pct, "sla_pct": sla_pct,
        }

    def _avg_wpi(pid: str | None):
        lst = wpi_by_party.get(pid, [])
        return round(sum(lst) / len(lst), 2) if lst else None

    parties = []
    for r in party_rows:
        pid = str(r.id)
        count = r.ward_count or 0
        pct = round((count / total_wards) * 100, 1) if total_wards > 0 else 0
        metrics = _metrics_for_party(pid)
        parties.append({
            "id": pid,
            "name": r.name,
            "short_code": r.short_code or "",
            "color": r.color or "#9ca3af",
            "ward_count": count,
            "ward_pct": pct,
            "metrics": metrics,
            "avg_wpi": _avg_wpi(pid),
        })

    # Sort by ward count desc
    parties.sort(key=lambda x: x["ward_count"], reverse=True)

    wards_without_party = total_wards - sum(p["ward_count"] for p in parties)
    unassigned_pct = round((wards_without_party / total_wards) * 100, 1) if total_wards > 0 else 0
    unassigned_metrics = _metrics_for_party(None)
    unassigned_avg_wpi = _avg_wpi(None)

    return {
        "parties": parties,
        "total_wards": total_wards,
        "wards_without_party": wards_without_party,
        "unassigned_pct": unassigned_pct,
        "unassigned_metrics": unassigned_metrics,
        "unassigned_avg_wpi": unassigned_avg_wpi,
        "wards": [
            {
                "id": str(r.id),
                "name": r.name,
                "number": r.number,
                "party_id": str(r.party_id) if r.party_id else None,
                "party_color": r.color or "#9ca3af",
                "party_short_code": r.short_code or "",
            }
            for r in ward_rows
        ],
    }


@router.get(
    "/zones",
    summary="Review zone performance",
    description="Get a high-level view of how different zones are performing. Zone Performance Index = Σ(Ward Scores) / Number of Wards.",
    operation_id="fetchZonePerformanceComparison",
)
async def get_zone_analytics(db: AsyncSession = Depends(get_db)):
    """Returns list of zones. Zone Performance Index = avg of Ward Performance Index for wards in that zone."""
    # Get all ward analytics (Ward Performance Index per ward)
    ward_analytics = await get_ward_analytics(db, zone_id=None)

    # Group ward WPIs by zone_id
    zone_ward_scores: Dict[str, List[float]] = {}
    for w in ward_analytics:
        zid = w.get("zone_id")
        if zid is None:
            continue
        if zid not in zone_ward_scores:
            zone_ward_scores[zid] = []
        zone_ward_scores[zid].append(w["scores"]["wpi"])

    # Zone-level totals (all grievances in zone)
    query = (
        select(
            Zone.id,
            Zone.name,
            Zone.code,
            func.count(Grievance.id).label("total"),
            func.sum(case((Grievance.status == "resolved", 1), else_=0)).label("resolved"),
            func.sum(case((and_(Grievance.id != None, Grievance.status != "resolved"), 1), else_=0)).label("pending"),
            func.sum(case((and_(Grievance.status == "resolved", Grievance.updated_at - Grievance.created_at <= timedelta(hours=SLA_HOURS)), 1), else_=0)).label("sla_resolved"),
            func.sum(case((Grievance.status == "escalated", 1), else_=0)).label("escalated"),
        )
        .select_from(Zone)
        .join(Ward, Ward.zone_id == Zone.id, isouter=True)
        .join(Grievance, Grievance.ward_id == Ward.id, isouter=True)
        .group_by(Zone.id, Zone.name, Zone.code)
    )

    result = await db.execute(query)
    rows = result.all()

    analytics = []
    for row in rows:
        t = row.total or 0
        r = row.resolved or 0
        p = row.pending or 0
        s_count = row.sla_resolved or 0
        e = row.escalated or 0

        # Zone Performance Index = Σ(Ward Scores) / Number of Wards
        zid = str(row.id)
        ward_scores = zone_ward_scores.get(zid, [])
        if ward_scores:
            dpi = sum(ward_scores) / len(ward_scores)
        else:
            dpi = 70.0  # Baseline when zone has no wards with activity

        resolution_rate = r / t if t > 0 else 0
        sla_rate = s_count / r if r > 0 else 1.0
        pending_score = 1 - (p / t) if t > 0 else 1
        escalation_score = 1 - (e / t) if t > 0 else 1

        performance = "Excellent"
        if dpi < 60:
            performance = "Critical"
        elif dpi < 70:
            performance = "Poor"
        elif dpi < 80:
            performance = "Average"
        elif dpi < 90:
            performance = "Good"

        analytics.append({
            "id": zid,
            "name": row.name,
            "code": row.code,
            "metrics": {
                "total": t,
                "resolved": r,
                "pending": p,
                "sla_resolved": s_count,
                "escalated": e,
            },
            "scores": {
                "resolution_rate": round(resolution_rate, 4),
                "sla_rate": round(sla_rate, 4),
                "pending_score": round(pending_score, 4),
                "escalation_score": round(escalation_score, 4),
                "zpi": round(dpi, 2),
            },
            "performance": performance,
        })

    analytics.sort(key=lambda x: x["scores"]["zpi"], reverse=True)
    return analytics

@router.get(
    "/escalations",
    summary="Escalation analytics",
    description="Aggregated escalation metrics by zone, ward, department, and priority.",
    operation_id="fetchEscalationAnalytics",
)
async def get_escalation_analytics(
    db: AsyncSession = Depends(get_db),
    zone_id: Annotated[uuid.UUID | None, Query(description="Filter by zone UUID.")] = None,
    ward_id: Annotated[uuid.UUID | None, Query(description="Filter by ward UUID.")] = None,
    category_dept: Annotated[
        uuid.UUID | None, Query(description="Filter by department (category dept) UUID.")
    ] = None,
    priority: Annotated[str | None, Query(description="Filter by base priority level.")] = None,
):
    """Returns escalation counts by zone, ward, department, priority for charts and insights."""
    # By zone
    zone_q = (
        select(Zone.id, Zone.name, Zone.code, func.count(Grievance.id).label("count"))
        .select_from(Grievance)
        .join(Ward, Grievance.ward_id == Ward.id)
        .join(Zone, Ward.zone_id == Zone.id)
        .where(Grievance.status == "escalated")
    )
    if zone_id:
        zone_q = zone_q.where(Zone.id == zone_id)
    if ward_id:
        zone_q = zone_q.where(Grievance.ward_id == ward_id)
    if category_dept:
        zone_q = zone_q.join(GrievanceCategory, Grievance.category_id == GrievanceCategory.id).where(GrievanceCategory.dept_id == category_dept)
    if priority:
        zone_q = zone_q.where(Grievance.priority == priority)
    zone_q = zone_q.group_by(Zone.id, Zone.name, Zone.code)
    zone_rows = (await db.execute(zone_q)).all()

    # By ward
    ward_q = (
        select(Ward.id, Ward.name, Ward.number, Ward.zone_id, func.count(Grievance.id).label("count"))
        .select_from(Grievance)
        .join(Ward, Grievance.ward_id == Ward.id)
        .where(Grievance.status == "escalated")
    )
    if zone_id:
        ward_q = ward_q.where(Ward.zone_id == zone_id)
    if ward_id:
        ward_q = ward_q.where(Grievance.ward_id == ward_id)
    if category_dept:
        ward_q = ward_q.join(GrievanceCategory, Grievance.category_id == GrievanceCategory.id).where(GrievanceCategory.dept_id == category_dept)
    if priority:
        ward_q = ward_q.where(Grievance.priority == priority)
    ward_q = ward_q.group_by(Ward.id, Ward.name, Ward.number, Ward.zone_id)
    ward_rows = (await db.execute(ward_q)).all()

    zone_ids = {r.zone_id for r in ward_rows if r.zone_id}
    zone_names = {}
    if zone_ids:
        zn = (await db.execute(select(Zone.id, Zone.name).where(Zone.id.in_(zone_ids)))).all()
        zone_names = {str(r.id): r.name for r in zn}

    # By department
    dept_q = (
        select(Department.id, Department.name, func.count(Grievance.id).label("count"))
        .select_from(Grievance)
        .join(GrievanceCategory, Grievance.category_id == GrievanceCategory.id)
        .join(Department, GrievanceCategory.dept_id == Department.id)
        .where(Grievance.status == "escalated")
    )
    if zone_id:
        dept_q = dept_q.join(Ward, Grievance.ward_id == Ward.id).where(Ward.zone_id == zone_id)
    if ward_id:
        dept_q = dept_q.where(Grievance.ward_id == ward_id)
    if category_dept:
        dept_q = dept_q.where(GrievanceCategory.dept_id == category_dept)
    if priority:
        dept_q = dept_q.where(Grievance.priority == priority)
    dept_q = dept_q.group_by(Department.id, Department.name)
    dept_rows = (await db.execute(dept_q)).all()

    # By effective priority (stored priority + reopen_count: reopens bump severity)
    rc = func.coalesce(Grievance.reopen_count, 0)
    pri = func.coalesce(cast(Grievance.priority, String), "medium")
    eff_pri = case(
        (rc >= 2, "high"),
        ((rc == 1) & (pri.in_(["medium", "high"])), "high"),
        ((rc == 1) & (pri == "low"), "medium"),
        else_=pri,
    )
    pri_q = select(eff_pri.label("effective_priority"), func.count(Grievance.id).label("count")).where(
        Grievance.status == "escalated"
    )
    if zone_id:
        pri_q = pri_q.join(Ward, Grievance.ward_id == Ward.id).where(Ward.zone_id == zone_id)
    if ward_id:
        pri_q = pri_q.where(Grievance.ward_id == ward_id)
    if category_dept:
        pri_q = pri_q.join(GrievanceCategory, Grievance.category_id == GrievanceCategory.id).where(GrievanceCategory.dept_id == category_dept)
    if priority:
        pri_q = pri_q.where(Grievance.priority == priority)
    pri_q = pri_q.group_by(eff_pri)
    pri_rows = (await db.execute(pri_q)).all()

    total_q = select(func.count(Grievance.id)).where(Grievance.status == "escalated")
    if zone_id:
        total_q = total_q.join(Ward, Grievance.ward_id == Ward.id).where(Ward.zone_id == zone_id)
    if ward_id:
        total_q = total_q.where(Grievance.ward_id == ward_id)
    if category_dept:
        total_q = total_q.join(GrievanceCategory, Grievance.category_id == GrievanceCategory.id).where(GrievanceCategory.dept_id == category_dept)
    if priority:
        total_q = total_q.where(Grievance.priority == priority)
    total = (await db.scalar(total_q)) or 0

    by_priority = {str(r[0] or "medium"): r.count for r in pri_rows}

    # Reopened (escalated with reopen_count > 0)
    reopen_q = select(func.count(Grievance.id)).where(
        Grievance.status == "escalated",
        func.coalesce(Grievance.reopen_count, 0) > 0,
    )
    if zone_id:
        reopen_q = reopen_q.join(Ward, Grievance.ward_id == Ward.id).where(Ward.zone_id == zone_id)
    if ward_id:
        reopen_q = reopen_q.where(Grievance.ward_id == ward_id)
    if category_dept:
        reopen_q = reopen_q.join(GrievanceCategory, Grievance.category_id == GrievanceCategory.id).where(GrievanceCategory.dept_id == category_dept)
    if priority:
        reopen_q = reopen_q.where(Grievance.priority == priority)
    reopened_count = (await db.scalar(reopen_q)) or 0

    # Oldest escalation (days since creation)
    oldest_q = select(func.min(Grievance.created_at)).where(Grievance.status == "escalated")
    if zone_id:
        oldest_q = oldest_q.join(Ward, Grievance.ward_id == Ward.id).where(Ward.zone_id == zone_id)
    if ward_id:
        oldest_q = oldest_q.where(Grievance.ward_id == ward_id)
    if category_dept:
        oldest_q = oldest_q.join(GrievanceCategory, Grievance.category_id == GrievanceCategory.id).where(GrievanceCategory.dept_id == category_dept)
    if priority:
        oldest_q = oldest_q.where(Grievance.priority == priority)
    oldest_ts = await db.scalar(oldest_q)
    oldest_days = None
    if oldest_ts:
        delta = datetime.now(timezone.utc) - (oldest_ts if oldest_ts.tzinfo else oldest_ts.replace(tzinfo=timezone.utc))
        oldest_days = delta.days

    # --- NEW: EPS Level Distribution Calculation ---
    all_griev_q = select(
        Grievance.id, Grievance.created_at, Grievance.reopen_count, 
        Grievance.upvotes_count, Grievance.downvotes_count, Grievance.priority, 
        Grievance.ward_id
    ).where(Grievance.status == "escalated")
    
    if zone_id:
        all_griev_q = all_griev_q.join(Ward, Grievance.ward_id == Ward.id).where(Ward.zone_id == zone_id)
    if ward_id:
        all_griev_q = all_griev_q.where(Grievance.ward_id == ward_id)
    if category_dept:
        all_griev_q = all_griev_q.join(GrievanceCategory, Grievance.category_id == GrievanceCategory.id).where(GrievanceCategory.dept_id == category_dept)
    if priority:
        all_griev_q = all_griev_q.where(Grievance.priority == priority)
        
    all_griev_rows = (await db.execute(all_griev_q)).all()
    
    eps_dist = {"Critical": 0, "High": 0, "Moderate": 0, "Low": 0}
    ward_eps_sums = {} # ward_id -> [sum_eps, count]
    
    if all_griev_rows:
        ward_ids_active = {r.ward_id for r in all_griev_rows if r.ward_id}
        maxima = await get_ward_maxima(db, list(ward_ids_active))
        
        for g in all_griev_rows:
            m = maxima.get(g.ward_id, {"max_age": 1.0, "max_netvotes": 1.0})
            class _G:
                def __init__(self, r):
                    self.created_at = r.created_at
                    self.reopen_count = r.reopen_count
                    self.upvotes_count = r.upvotes_count
                    self.downvotes_count = r.downvotes_count
                    self.priority = r.priority
            
            eps_res = calculate_eps(_G(g), m["max_age"], m["max_netvotes"])
            score = eps_res["total"]
            
            if score >= 75: eps_dist["Critical"] += 1
            elif score >= 50: eps_dist["High"] += 1
            elif score >= 25: eps_dist["Moderate"] += 1
            else: eps_dist["Low"] += 1
            
            if g.ward_id:
                if g.ward_id not in ward_eps_sums: ward_eps_sums[g.ward_id] = [0.0, 0]
                ward_eps_sums[g.ward_id][0] += score
                ward_eps_sums[g.ward_id][1] += 1

    # Format Top Wards by Avg EPS
    avg_eps_wards = []
    if ward_eps_sums:
        ward_names = {}
        wn_res = await db.execute(select(Ward.id, Ward.name).where(Ward.id.in_(list(ward_eps_sums.keys()))))
        ward_names = {r.id: r.name for r in wn_res.all()}
        
        for w_id, data in ward_eps_sums.items():
            avg_score = data[0] / data[1]
            avg_eps_wards.append({"id": str(w_id), "name": ward_names.get(w_id, "–"), "avg_eps": round(avg_score, 1)})
    
    avg_eps_wards.sort(key=lambda x: x["avg_eps"], reverse=True)
    top_risk_wards = avg_eps_wards[:5]

    return {
        "total": total,
        "reopened_count": reopened_count,
        "oldest_days": oldest_days,
        "eps_distribution": eps_dist,
        "top_risk_wards": top_risk_wards,
        "by_zone": [{"id": str(r.id), "name": r.name, "code": r.code, "count": r.count} for r in zone_rows],
        "by_ward": [
            {
                "id": str(r.id),
                "name": r.name,
                "number": r.number,
                "zone_name": zone_names.get(str(r.zone_id), "–") if r.zone_id else "–",
                "count": r.count,
            }
            for r in ward_rows
        ],
        "by_department": [{"id": str(r.id), "name": r.name, "count": r.count} for r in dept_rows],
        "by_priority": {
            "high": by_priority.get("high", 0),
            "medium": by_priority.get("medium", 0),
            "low": by_priority.get("low", 0),
        },
    }


@router.get(
    "/grievances/escalation-priority",
    summary="Escalation Priority Score (EPS) per grievance",
    description=(
        "Computes a composite Escalation Priority Score (0–100) for each escalated grievance. "
        "EPS = Escalation Age (30%) + Reopen Frequency (25%) + Net Votes Impact (25%) + Grievance Severity Level (20%). "
        "Results are sorted by EPS descending so the most critical grievances appear first."
    ),
    operation_id="fetchGrievanceEscalationPriority",
)
async def get_grievance_escalation_priority(
    db: AsyncSession = Depends(get_db),
    zone_id: uuid.UUID | None = Query(None, description="Filter by zone UUID."),
    ward_id: uuid.UUID | None = Query(None, description="Filter by ward UUID."),
    category_dept: uuid.UUID | None = Query(None, description="Filter by department (category dept) UUID."),
    priority: str | None = Query(None, description="Filter by base priority level."),
):
    """
    Escalation Priority Score (EPS) per escalated grievance.
    """
    print(f"DEBUG: get_grievance_escalation_priority called with {ward_id=}, {zone_id=}")
    MAX_REOPEN = 3
    now = datetime.now(timezone.utc)

    # ── Step 1: Fetch unique escalated grievance IDs ─────────────────────────────
    id_q = select(Grievance.id).where(Grievance.status == "escalated").distinct()
    
    # Filter by ward/zone at the ID level too for performance
    if ward_id is not None:
        id_q = id_q.where(Grievance.ward_id == ward_id)
    elif zone_id is not None:
        id_q = id_q.join(Ward, Grievance.ward_id == Ward.id).where(Ward.zone_id == zone_id)
        
    if category_dept is not None:
        id_q = id_q.join(GrievanceCategory, Grievance.category_id == GrievanceCategory.id).where(GrievanceCategory.dept_id == category_dept)
        
    if priority is not None:
        id_q = id_q.where(Grievance.priority == priority)

    id_rows = (await db.execute(id_q)).all()
    if not id_rows:
        return []
    ids = [r.id for r in id_rows]

    # Scalar subqueries for current attribution
    worker_sub = (
        select(User.name)
        .select_from(Assignment)
        .join(User, Assignment.assigned_to_id == User.id)
        .where(Assignment.grievance_id == Grievance.id)
        .order_by(Assignment.assigned_at.desc())
        .limit(1)
        .correlate(Grievance)
        .scalar_subquery()
    )
    
    manager_sub = (
        select(User.name)
        .select_from(Assignment)
        .join(User, Assignment.assigned_by_id == User.id)
        .where(Assignment.grievance_id == Grievance.id)
        .order_by(Assignment.assigned_at.desc())
        .limit(1)
        .correlate(Grievance)
        .scalar_subquery()
    )

    griev_q = (
        select(Grievance)
        .options(
            selectinload(Grievance.ward).selectinload(Ward.zone),
            selectinload(Grievance.category).selectinload(GrievanceCategory.department)
        )
        .add_columns(
            worker_sub.label("worker_name"),
            manager_sub.label("manager_name"),
        )
        .where(Grievance.id.in_(ids))
    )
    
    res = await db.execute(griev_q)
    griev_rows = res.unique().all()

    if not griev_rows:
        return []

    # ── Step 2: Compute per-ward maxima ──────────────────────────────────────────
    ward_ids_in_set = {r[0].ward_id for r in griev_rows if r[0].ward_id is not None}
    maxima = await get_ward_maxima(db, list(ward_ids_in_set))

    # ── Step 3: Score each grievance ──────────────────────────────────────────
    results = []
    for row in griev_rows:
        g = row[0]  # The Grievance object
        worker_name = row.worker_name
        manager_name = row.manager_name
        
        # Score each grievance
        m = maxima.get(g.ward_id, {"max_age": 1.0, "max_netvotes": 1.0})
        eps_data = calculate_eps(g, m["max_age"], m["max_netvotes"])
        total = eps_data["total"]
        
        # Escalation level label
        if total >= 75:
            level = "Critical"
        elif total >= 50:
            level = "High"
        elif total >= 25:
            level = "Moderate"
        else:
            level = "Low"

        ward_name = g.ward.name if g.ward else "–"
        ward_num = g.ward.number if g.ward else None
        zone_name = g.ward.zone.name if g.ward and g.ward.zone else "–"
        dept_name = g.category.department.name if g.category and g.category.department else "–"
        cat_name = g.category.name if g.category else "–"

        # Final object preparation for Admin Panel
        results.append({
            "id": str(g.id),
            "title": g.title or "(untitled)",
            "status": str(g.status.value if hasattr(g.status, "value") else g.status),
            "priority": str(g.priority.value if hasattr(g.priority, "value") else g.priority).lower(),
            "department": dept_name,
            "category": cat_name,
            "ward": f"#{ward_num} {ward_name}" if ward_num else ward_name,
            "zone": zone_name,
            "worker": worker_name or "Unassigned",
            "manager": manager_name or "–",
            "eps": eps_data,
            "escalation_level": level,
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "reopen_count": g.reopen_count or 0,
            "upvotes": g.upvotes_count or 0,
            "downvotes": g.downvotes_count or 0,
        })

    results.sort(key=lambda x: x["eps"]["total"], reverse=True)
    return results


def _cis_raw_metrics_for_json(raw: dict | None) -> dict[str, int]:
    """Keep only numeric values as ints for API clients (e.g. Flutter parses ints)."""
    out: dict[str, int] = {}
    for k, v in (raw or {}).items():
        if isinstance(v, bool):
            out[k] = int(v)
        elif isinstance(v, (int, float)):
            out[k] = int(v)
    return out


@router.get(
    "/cis/{user_id}",
    summary="Civic Impact Score (CIS)",
    description=(
        "Returns the latest stored CIS snapshot (rolling period, IST calendar dates on snapshot). "
        "Use `legacy=true` for on-demand **all-time** calculation."
    ),
    operation_id="fetchCivicImpactScore",
)
async def get_civic_impact_score(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    legacy: bool = Query(
        False,
        description="If true, compute all-time CIS live (not from weekly snapshots).",
    ),
):
    user_q = select(User).where(User.id == user_id)
    user_res = await db.execute(user_q)
    user = user_res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if legacy:
        return await calculate_user_cis(db, user)

    snap = await fetch_latest_cis_snapshot(db, user_id)
    if snap is None:
        return {
            "source": "pending",
            "total_score": 0,
            "breakdown": {},
            "raw_metrics": {},
        }

    bd = snap.breakdown or {}
    return {
        "source": "weekly_snapshot",
        "week_start": snap.week_start.isoformat(),
        "week_end": snap.week_end.isoformat(),
        "computed_at": snap.computed_at.isoformat() if snap.computed_at else None,
        "total_score": float(snap.total_score) if snap.total_score is not None else 0.0,
        "breakdown": {str(k): float(v) for k, v in bd.items()},
        "raw_metrics": _cis_raw_metrics_for_json(snap.raw_metrics if isinstance(snap.raw_metrics, dict) else None),
    }


@router.get(
    "/cis/schedule",
    summary="CIS automatic schedule (admin)",
    description=(
        "Next scheduled CIS run (IST) and last run time. Rolling window uses last global run "
        "with a 7-day cap; manual “Update CIS” resets the next automatic run to now + 7 days."
    ),
    operation_id="getCisSchedule",
)
async def get_cis_schedule(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    st = await get_cis_scheduler_state(db)
    return {
        "timezone": "Asia/Kolkata",
        "last_run_at_ist": format_iso_ist(st.last_run_at) if st.last_run_at else None,
        "last_run_display": format_datetime_display_ist(st.last_run_at) if st.last_run_at else None,
        "next_run_at_ist": format_iso_ist(st.next_run_at) if st.next_run_at else None,
        "next_run_display": format_datetime_display_ist(st.next_run_at) if st.next_run_at else None,
    }


@router.post(
    "/cis/recompute-weekly",
    summary="Recompute CIS snapshots (admin)",
    description=(
        "For every citizen, computes CIS for the current rolling period (from last global run, "
        "max 7 days of activity, Indian Standard Time) and upserts snapshots. "
        "Sets next automatic run to now + 7 days (IST). **Admin only.**"
    ),
    operation_id="adminRecomputeWeeklyCisSnapshots",
)
async def post_recompute_weekly_cis_snapshots(
    _admin: User = Depends(require_admin),
):
    return await compute_cis_snapshots()


@router.get(
    "/citizens/cis-leaderboard",
    summary="Citizen Civic Impact Score — top & bottom",
    description=(
        "Returns the top 10 and bottom 5 citizens by **latest stored** CIS snapshot "
        "(IST period labels; same scores as the Citizens admin column). Manager/admin only."
    ),
    operation_id="fetchCitizenCisLeaderboard",
)
async def get_citizen_cis_leaderboard_endpoint(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    return await fetch_citizen_cis_leaderboard(db)


@router.get(
    "/sustainability",
    summary="Sustainability report",
    description="Department-wise SDG mapping and Sustainability Index based on departmental performance.",
    operation_id="fetchSustainabilityProgressReport",
)
async def get_sustainability_analytics(
    db: AsyncSession = Depends(get_db),
    ward_id: uuid.UUID | None = Query(
        None, description="Optional ward UUID filter (same scope as Department analytics)."
    ),
    zone_id: uuid.UUID | None = Query(
        None, description="Optional zone UUID filter (same scope as Department analytics)."
    ),
):
    def _split_sdgs(raw: str | None) -> list[str]:
        if not raw:
            return []
        return [p.strip() for p in str(raw).split(",") if p and p.strip()]

    dept_rows = await get_department_analytics(db=db, ward_id=ward_id, zone_id=zone_id)
    dept_meta_rows = (
        await db.execute(
            select(Department.id, Department.sdg, Department.description, Department.name)
        )
    ).all()
    dept_meta_map = {
        str(r.id): {
            "sdg": (r.sdg or "").strip() if r.sdg else None,
            "description": (r.description or "").strip() if r.description else None,
            "name": r.name,
        }
        for r in dept_meta_rows
    }

    department_rows: list[dict[str, Any]] = []
    by_sdg: dict[str, dict[str, Any]] = {}
    mapped_dept_ids: set[str] = set()
    mapped_dept_dpi: dict[str, float] = {}
    for d in dept_rows:
        dept_id = str(d.get("id"))
        meta = dept_meta_map.get(dept_id, {})
        sustainability_index = float(d.get("scores", {}).get("dpi", 0))
        entry = {
            "id": dept_id,
            "department_name": d.get("name") or meta.get("name") or "Unknown",
            "sdg": meta.get("sdg"),
            "description": meta.get("description"),
            "sustainability_index": round(sustainability_index, 2),
            "performance": d.get("performance", "Average"),
            "metrics": d.get("metrics", {}),
            "scores": d.get("scores", {}),
        }
        department_rows.append(entry)

        sdgs = _split_sdgs(meta.get("sdg"))
        if not sdgs:
            sdgs = ["Unmapped"]
        else:
            mapped_dept_ids.add(dept_id)
            mapped_dept_dpi[dept_id] = sustainability_index

        for sdg in sdgs:
            bucket = by_sdg.setdefault(
                sdg,
                {
                    "sdg": sdg,
                    "department_ids": set(),
                    "department_names": set(),
                    "descriptions": set(),
                    "_sum_si": 0.0,
                    "_max_si": 0.0,
                },
            )
            bucket["department_ids"].add(dept_id)
            bucket["department_names"].add(entry["department_name"])
            if entry.get("description"):
                bucket["descriptions"].add(str(entry["description"]))
            bucket["_sum_si"] += sustainability_index
            bucket["_max_si"] = max(bucket["_max_si"], sustainability_index)

    rows = []
    for item in by_sdg.values():
        count = len(item["department_ids"])
        names = sorted(item["department_names"])
        descriptions = sorted(item["descriptions"])
        rows.append(
            {
                "sdg": item["sdg"],
                "description": "; ".join(descriptions) if descriptions else None,
                "department_count": count,
                "sustainability_index": round(
                    (item["_sum_si"] / count) if count else 0.0, 2
                ),
                "max_sustainability_index": round(item["_max_si"], 2),
                "mapped_departments": names,
                "mapped_departments_text": ", ".join(names),
            }
        )
    rows.sort(key=lambda x: x["sustainability_index"], reverse=True)

    return {
        "rows": rows,
        "sdg_summary": rows,
        "department_rows": department_rows,
        "totals": {
            "departments": len(department_rows),
            "mapped_departments": len(mapped_dept_ids),
            "unmapped_departments": max(0, len(department_rows) - len(mapped_dept_ids)),
            "sdg_groups": len([r for r in rows if r.get("sdg") != "Unmapped"]),
            "average_sustainability_index": round(
                (sum(mapped_dept_dpi.values()) / len(mapped_dept_dpi))
                if mapped_dept_dpi
                else 0.0,
                2,
            ),
        },
        "method_note": "Sustainability analytics are SDG-centric; comma-separated department SDGs are split and aggregated per SDG.",
    }


async def _build_analytics_report_pdf_bytes(
    db: AsyncSession,
    user: User,
    dept_zone_id: uuid.UUID | None,
    dept_ward_id: uuid.UUID | None,
    ward_zone_id: uuid.UUID | None,
    department_id: uuid.UUID | None,
    worker_ward_id: uuid.UUID | None,
    period_start: date,
    period_end: date,
) -> bytes:
    dept_rows = await get_department_analytics(
        db=db, ward_id=dept_ward_id, zone_id=dept_zone_id
    )
    worker_rows = await get_worker_analytics(
        db=db,
        user=user,
        department_id=department_id,
        ward_id=worker_ward_id,
        from_date=period_start,
        to_date=period_end,
    )
    ward_rows = await get_ward_analytics(db=db, zone_id=ward_zone_id)
    zone_rows = await get_zone_analytics(db=db)
    esc = await get_escalation_analytics(
        db=db, zone_id=dept_zone_id, ward_id=dept_ward_id
    )
    sust = await get_sustainability_analytics(
        db=db,
        ward_id=dept_ward_id,
        zone_id=dept_zone_id,
    )
    party_control = await get_party_control_analytics(db)
    citizen_cis = await fetch_citizen_cis_leaderboard(db)

    ward_geojson: dict | None = None
    try:
        from app.api.v1.endpoints.wards import _load_ward_geojson

        ward_geojson = _load_ward_geojson()
    except Exception:
        ward_geojson = None

    filter_bits = [
        f"Dept / escalations — zone: {dept_zone_id or 'all'}, ward: {dept_ward_id or 'all'}",
        f"Wards section — zone: {ward_zone_id or 'all'}",
        f"Officers — dept: {department_id or 'all'}, ward: {worker_ward_id or 'all'}, "
        f"period: {period_start.isoformat()} … {period_end.isoformat()}",
    ]
    filters_note = " | ".join(filter_bits)

    return build_performance_report_pdf(
        title="CivicCare — Municipal performance analytics (full report)",
        generated_at=datetime.now(timezone.utc),
        filters_note=filters_note,
        department_rows=dept_rows,
        worker_rows=worker_rows,
        ward_rows=ward_rows,
        zone_rows=zone_rows,
        escalation=esc if isinstance(esc, dict) else {},
        sustainability=sust if isinstance(sust, dict) else {"message": str(sust)},
        party_control=party_control if isinstance(party_control, dict) else {},
        ward_geojson=ward_geojson,
        citizen_cis=citizen_cis if isinstance(citizen_cis, dict) else {},
    )

@router.get(
    "/performance-report.pdf",
    summary="Download full analytics performance report (PDF)",
    description=(
        "Single multi-section PDF: departments, officers (period metrics), wards, zones, escalations, sustainability. "
        "Uses the same filters as the admin Analytics page (dept zone/ward, ward tab zone, officer dept/ward/period)."
    ),
    operation_id="downloadAnalyticsPerformanceReportPdf",
)
async def download_performance_report_pdf(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
    dept_zone_id: uuid.UUID | None = Query(
        None, description="Department & escalation scope: zone (matches Departments tab)"
    ),
    dept_ward_id: uuid.UUID | None = Query(
        None, description="Department & escalation scope: ward (matches Departments tab)"
    ),
    ward_zone_id: uuid.UUID | None = Query(
        None, description="Wards section: filter by zone (matches Wards tab)"
    ),
    department_id: uuid.UUID | None = Query(
        None, description="Officers section: department filter"
    ),
    worker_ward_id: uuid.UUID | None = Query(
        None, description="Officers section: ward filter"
    ),
    from_date: date | None = Query(None, description="Officers period start (YYYY-MM-DD)"),
    to_date: date | None = Query(None, description="Officers period end (YYYY-MM-DD)"),
):
    """Build one PDF from existing analytics endpoints (admin panel only; requires manager JWT)."""
    period_end = to_date or date.today()
    period_start = from_date
    if period_start is None:
        period_start = period_end - timedelta(days=30)
    pdf_bytes = await _build_analytics_report_pdf_bytes(
        db=db,
        user=user,
        dept_zone_id=dept_zone_id,
        dept_ward_id=dept_ward_id,
        ward_zone_id=ward_zone_id,
        department_id=department_id,
        worker_ward_id=worker_ward_id,
        period_start=period_start,
        period_end=period_end,
    )

    filename = f"civiccare-analytics-report-{period_end.isoformat()}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/performance-report/email",
    summary="Email full analytics performance report (PDF)",
    description=(
        "Generates the same multi-section analytics PDF and emails it as an attachment "
        "to ANALYTICS_REPORT_ADMIN_EMAIL. Requires SMTP settings."
    ),
    operation_id="emailAnalyticsPerformanceReportPdf",
)
async def email_performance_report_pdf(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
    dept_zone_id: uuid.UUID | None = Query(None),
    dept_ward_id: uuid.UUID | None = Query(None),
    ward_zone_id: uuid.UUID | None = Query(None),
    department_id: uuid.UUID | None = Query(None),
    worker_ward_id: uuid.UUID | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
):
    period_end = to_date or date.today()
    period_start = from_date or (period_end - timedelta(days=30))
    recipient = settings.ANALYTICS_REPORT_ADMIN_EMAIL.strip()
    sender = settings.SMTP_FROM_EMAIL.strip()
    if not recipient:
        raise HTTPException(400, "ANALYTICS_REPORT_ADMIN_EMAIL is not configured")
    if not sender or not settings.SMTP_HOST or not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        raise HTTPException(400, "SMTP settings are not fully configured")

    pdf_bytes = await _build_analytics_report_pdf_bytes(
        db=db,
        user=user,
        dept_zone_id=dept_zone_id,
        dept_ward_id=dept_ward_id,
        ward_zone_id=ward_zone_id,
        department_id=department_id,
        worker_ward_id=worker_ward_id,
        period_start=period_start,
        period_end=period_end,
    )
    filename = f"civiccare-analytics-report-{period_end.isoformat()}.pdf"

    msg = EmailMessage()
    msg["Subject"] = f"CivicCare Analytics Report ({period_start.isoformat()} to {period_end.isoformat()})"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(
        "Attached is the latest CivicCare analytics report PDF from the admin portal."
    )
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=filename,
    )

    def _send():
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as s:
            if settings.SMTP_USE_TLS:
                s.starttls()
            s.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            s.send_message(msg)

    try:
        await asyncio.to_thread(_send)
    except Exception as e:
        raise HTTPException(500, f"Failed to send email report: {e}")

    return {
        "ok": True,
        "sent_to": recipient,
        "filename": filename,
        "period": {"from": period_start.isoformat(), "to": period_end.isoformat()},
    }
