import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, select, cast, Date, union
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    User,
    Grievance,
    GrievanceVote,
    GrievanceComment,
    CivicImpactScoreSnapshot,
    CisSchedulerState,
)

# Indian Standard Time — all CIS scheduling and displayed period labels use IST.
IST = ZoneInfo("Asia/Kolkata")


def _ensure_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ist_inclusive_dates_for_period(period_start_utc: datetime, period_end_utc: datetime) -> tuple[date, date]:
    """
    Inclusive IST calendar dates for a half-open UTC period [period_start_utc, period_end_utc).
    Used for snapshot week_start / week_end columns (display labels).
    """
    ps = _ensure_aware_utc(period_start_utc)
    pe = _ensure_aware_utc(period_end_utc)
    d_start = ps.astimezone(IST).date()
    if pe <= ps:
        return d_start, d_start
    last_instant = pe - timedelta(microseconds=1)
    d_end = last_instant.astimezone(IST).date()
    return d_start, d_end


def format_iso_ist(dt: datetime) -> str:
    """ISO-8601 with +05:30 offset."""
    return _ensure_aware_utc(dt).astimezone(IST).isoformat(timespec="seconds")


def format_datetime_display_ist(dt: datetime) -> str:
    """Human-readable IST for PDF / UI."""
    return _ensure_aware_utc(dt).astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


async def get_cis_scheduler_state(db: AsyncSession) -> CisSchedulerState:
    """Singleton row id=1."""
    r = await db.execute(select(CisSchedulerState).where(CisSchedulerState.id == 1))
    row = r.scalar_one_or_none()
    if row is None:
        row = CisSchedulerState(id=1, last_run_at=None, next_run_at=None)
        db.add(row)
        await db.flush()
    return row


async def calculate_user_cis(db: AsyncSession, user: User) -> dict:
    """
    Calculate the Civic Impact Score (CIS) for a given citizen user (all-time window).
    The CIS quantifies a user's contribution using 5 weighted sub-metrics (max 100).
    """
    now = datetime.now(timezone.utc)
    delta = now - user.created_at
    days_since_registration = max(1, delta.days)

    grievances_q = select(
        func.count(Grievance.id),
        func.coalesce(func.sum(Grievance.upvotes_count), 0),
        func.sum(
            case(
                (
                    ((Grievance.downvotes_count >= 3)
                    & (Grievance.downvotes_count > Grievance.upvotes_count))
                    | (Grievance.is_ai_spam == True),
                    1,
                ),
                else_=0,
            )
        ),
    ).where(Grievance.reporter_id == user.id)

    res_gv = await db.execute(grievances_q)
    row_gv = res_gv.one()
    user_grievances = row_gv[0] or 0
    total_upvotes_received = row_gv[1] or 0
    spam_grievances = row_gv[2] or 0

    votes_q = select(func.count(GrievanceVote.id)).where(GrievanceVote.user_id == user.id)
    res_vc = await db.execute(votes_q)
    votes_cast_by_user = res_vc.scalar() or 0

    active_dates_subq = union(
        select(cast(Grievance.created_at, Date).label("d")).where(Grievance.reporter_id == user.id),
        select(cast(GrievanceVote.created_at, Date).label("d")).where(GrievanceVote.user_id == user.id),
        select(cast(GrievanceComment.created_at, Date).label("d")).where(GrievanceComment.user_id == user.id),
    ).subquery()
    active_days_q = select(func.count(func.distinct(active_dates_subq.c.d)))
    res_ad = await db.execute(active_days_q)
    active_days = res_ad.scalar() or 0

    ward_total_grievances = 0
    if user.ward_id:
        ward_q = select(func.count(Grievance.id)).where(Grievance.ward_id == user.ward_id)
        res_wt = await db.execute(ward_q)
        ward_total_grievances = res_wt.scalar() or 0

    return _cis_formula_dict(
        user_grievances=user_grievances,
        total_upvotes_received=int(total_upvotes_received),
        spam_grievances=int(spam_grievances or 0),
        votes_cast_by_user=int(votes_cast_by_user),
        active_days=int(active_days),
        period_days_for_ci=days_since_registration,
        ward_total_grievances=int(ward_total_grievances),
        all_time=True,
    )


def _cis_formula_dict(
    *,
    user_grievances: int,
    total_upvotes_received: int,
    spam_grievances: int,
    votes_cast_by_user: int,
    active_days: int,
    period_days_for_ci: int,
    ward_total_grievances: int,
    all_time: bool = False,
) -> dict:
    if ward_total_grievances > 0:
        wcr_raw = (user_grievances / ward_total_grievances) * 30.0
    else:
        wcr_raw = 0.0
    wcr = min(wcr_raw, 30.0)

    if user_grievances > 0:
        ugi_raw = (total_upvotes_received / user_grievances) * 20.0
    else:
        ugi_raw = 0.0
    ugi = min(ugi_raw, 20.0)

    if ward_total_grievances > 0:
        cvp_raw = (votes_cast_by_user / ward_total_grievances) * 20.0
    else:
        cvp_raw = 0.0
    cvp = min(cvp_raw, 20.0)

    denom_ci = max(1, period_days_for_ci)
    ci_raw = (active_days / denom_ci) * 15.0
    ci = min(ci_raw, 15.0)

    if user_grievances > 0:
        npf_raw = (1.0 - (spam_grievances / user_grievances)) * 15.0
    else:
        npf_raw = 15.0
    npf = max(0.0, min(npf_raw, 15.0))

    total_cis = wcr + ugi + cvp + ci + npf

    raw_metrics: dict = {
        "user_grievances": int(user_grievances),
        "ward_total_grievances": int(ward_total_grievances),
        "total_upvotes_received": int(total_upvotes_received),
        "votes_cast_by_user": int(votes_cast_by_user),
        "active_days": int(active_days),
        "spam_grievances": int(spam_grievances),
    }
    if all_time:
        raw_metrics["days_since_registration"] = int(denom_ci)
    else:
        raw_metrics["ci_denominator_days"] = int(denom_ci)

    return {
        "total_score": round(total_cis, 2),
        "breakdown": {
            "WCR": round(wcr, 2),
            "UGI": round(ugi, 2),
            "CVP": round(cvp, 2),
            "CI": round(ci, 2),
            "NPF": round(npf, 2),
        },
        "raw_metrics": raw_metrics,
    }


async def calculate_user_cis_for_period(
    db: AsyncSession,
    user: User,
    start: datetime,
    end: datetime,
) -> dict:
    """
    CIS for activity within [start, end) (UTC). Uses the same 5 components; denominators
    are scoped to this window (ward grievance counts, votes, etc.). CI uses active days
    in-window divided by the window length in days (min 1, typically 7 for weekly jobs).
    """
    period_days = max(1, int((end - start).total_seconds() // 86400))

    g_filter = and_(
        Grievance.reporter_id == user.id,
        Grievance.created_at >= start,
        Grievance.created_at < end,
    )
    grievances_q = select(
        func.count(Grievance.id),
        func.coalesce(func.sum(Grievance.upvotes_count), 0),
        func.sum(
            case(
                (
                    ((Grievance.downvotes_count >= 3)
                    & (Grievance.downvotes_count > Grievance.upvotes_count))
                    | (Grievance.is_ai_spam == True),
                    1,
                ),
                else_=0,
            )
        ),
    ).where(g_filter)

    res_gv = await db.execute(grievances_q)
    row_gv = res_gv.one()
    user_grievances = row_gv[0] or 0
    total_upvotes_received = int(row_gv[1] or 0)
    spam_grievances = int(row_gv[2] or 0)

    votes_q = select(func.count(GrievanceVote.id)).where(
        GrievanceVote.user_id == user.id,
        GrievanceVote.created_at >= start,
        GrievanceVote.created_at < end,
    )
    votes_cast_by_user = (await db.execute(votes_q)).scalar() or 0

    active_dates_subq = union(
        select(cast(Grievance.created_at, Date).label("d")).where(g_filter),
        select(cast(GrievanceVote.created_at, Date).label("d")).where(
            GrievanceVote.user_id == user.id,
            GrievanceVote.created_at >= start,
            GrievanceVote.created_at < end,
        ),
        select(cast(GrievanceComment.created_at, Date).label("d")).where(
            GrievanceComment.user_id == user.id,
            GrievanceComment.created_at >= start,
            GrievanceComment.created_at < end,
        ),
    ).subquery()
    active_days_q = select(func.count(func.distinct(active_dates_subq.c.d)))
    active_days = (await db.execute(active_days_q)).scalar() or 0

    ward_total_grievances = 0
    if user.ward_id:
        ward_q = select(func.count(Grievance.id)).where(
            Grievance.ward_id == user.ward_id,
            Grievance.created_at >= start,
            Grievance.created_at < end,
        )
        ward_total_grievances = (await db.execute(ward_q)).scalar() or 0

    out = _cis_formula_dict(
        user_grievances=int(user_grievances),
        total_upvotes_received=total_upvotes_received,
        spam_grievances=spam_grievances,
        votes_cast_by_user=int(votes_cast_by_user),
        active_days=int(active_days),
        period_days_for_ci=period_days,
        ward_total_grievances=int(ward_total_grievances),
        all_time=False,
    )
    out["raw_metrics"]["period_days"] = period_days
    return out


async def upsert_cis_snapshot(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    week_start: date,
    week_end: date,
    payload: dict,
) -> None:
    """Insert or update CIS snapshot for a user/week."""
    now = datetime.now(timezone.utc)
    insert_stmt = pg_insert(CivicImpactScoreSnapshot).values(
        id=uuid.uuid4(),
        user_id=user_id,
        week_start=week_start,
        week_end=week_end,
        total_score=Decimal(str(payload["total_score"])),
        breakdown=payload["breakdown"],
        raw_metrics=payload["raw_metrics"],
        computed_at=now,
    )
    ex = insert_stmt.excluded
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["user_id", "week_start"],
        set_={
            "week_end": ex.week_end,
            "total_score": ex.total_score,
            "breakdown": ex.breakdown,
            "raw_metrics": ex.raw_metrics,
            "computed_at": ex.computed_at,
        },
    )
    await db.execute(upsert_stmt)


def _is_missing_cis_table_error(exc: BaseException) -> bool:
    parts = [str(exc), repr(exc)]
    orig = getattr(exc, "orig", None)
    if orig is not None:
        parts.append(str(orig))
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        parts.append(str(cause))
    msg = " ".join(parts).lower()
    return "civic_impact_score_snapshots" in msg and (
        "does not exist" in msg or "undefinedtable" in msg.replace(" ", "")
    )


async def fetch_latest_cis_snapshot(db: AsyncSession, user_id: uuid.UUID) -> CivicImpactScoreSnapshot | None:
    q = (
        select(CivicImpactScoreSnapshot)
        .where(CivicImpactScoreSnapshot.user_id == user_id)
        .order_by(CivicImpactScoreSnapshot.week_start.desc())
        .limit(1)
    )
    try:
        res = await db.execute(q)
    except ProgrammingError as e:
        if _is_missing_cis_table_error(e):
            return None
        raise
    except Exception as e:
        if _is_missing_cis_table_error(e):
            return None
        raise
    return res.scalar_one_or_none()


async def fetch_latest_cis_snapshots_for_users(
    db: AsyncSession,
    user_ids: list[uuid.UUID],
) -> dict[uuid.UUID, CivicImpactScoreSnapshot]:
    """Latest snapshot per user (by week_start), for batch citizen lists."""
    if not user_ids:
        return {}
    q = select(CivicImpactScoreSnapshot).where(CivicImpactScoreSnapshot.user_id.in_(user_ids))
    try:
        res = await db.execute(q)
    except ProgrammingError as e:
        if _is_missing_cis_table_error(e):
            return {}
        raise
    except Exception as e:
        if _is_missing_cis_table_error(e):
            return {}
        raise
    rows = res.scalars().all()
    by_user: dict[uuid.UUID, CivicImpactScoreSnapshot] = {}
    for s in rows:
        cur = by_user.get(s.user_id)
        if cur is None or s.week_start > cur.week_start:
            by_user[s.user_id] = s
    return by_user


async def fetch_citizen_cis_leaderboard(
    db: AsyncSession,
    *,
    top_n: int = 10,
    bottom_n: int = 5,
) -> dict[str, Any]:
    """
    Latest weekly CIS snapshot per citizen. Returns top_n highest and bottom_n lowest scores.
    """
    try:
        mx_sub = (
            select(
                CivicImpactScoreSnapshot.user_id,
                func.max(CivicImpactScoreSnapshot.week_start).label("mx"),
            ).group_by(CivicImpactScoreSnapshot.user_id)
        ).subquery()

        q = (
            select(User, CivicImpactScoreSnapshot)
            .join(mx_sub, mx_sub.c.user_id == User.id)
            .join(
                CivicImpactScoreSnapshot,
                and_(
                    CivicImpactScoreSnapshot.user_id == User.id,
                    CivicImpactScoreSnapshot.week_start == mx_sub.c.mx,
                ),
            )
            .where(User.role == "citizen")
        )
        res = await db.execute(q)
        pairs = res.all()
    except ProgrammingError as e:
        if _is_missing_cis_table_error(e):
            return {"top": [], "bottom": [], "week_note": None}
        raise
    except Exception as e:
        if _is_missing_cis_table_error(e):
            return {"top": [], "bottom": [], "week_note": None}
        raise

    items: list[dict[str, Any]] = []
    for user, snap in pairs:
        ts = float(snap.total_score) if snap.total_score is not None else 0.0
        items.append(
            {
                "user_id": str(user.id),
                "name": user.name or "–",
                "phone": user.phone or "–",
                "ward": user.ward or "–",
                "zone": user.zone or "–",
                "cis_score": round(ts, 2),
                "week_start": snap.week_start.isoformat() if snap.week_start else None,
                "week_end": snap.week_end.isoformat() if snap.week_end else None,
                "computed_at": snap.computed_at.isoformat() if snap.computed_at else None,
            }
        )

    items.sort(key=lambda x: x["cis_score"], reverse=True)
    top = items[:top_n]
    items_asc = sorted(items, key=lambda x: x["cis_score"])
    bottom = items_asc[:bottom_n]

    week_note = None
    if items:
        week_note = (
            f"Scores from latest CIS snapshot (IST period {items[0]['week_start']} – {items[0]['week_end']}). "
            "Rolling window up to 7 days per update; schedule anchored to last run (Indian Standard Time)."
        )

    return {"top": top, "bottom": bottom, "week_note": week_note}
