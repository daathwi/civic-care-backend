"""Rolling CIS snapshots (IST labels): period from last global run, max 7 days; next auto-run +7d IST wall-clock."""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.db.database import AsyncSessionLocal
from app.models.models import User
from app.services.cis_service import (
    calculate_user_cis_for_period,
    format_datetime_display_ist,
    format_iso_ist,
    get_cis_scheduler_state,
    ist_inclusive_dates_for_period,
    upsert_cis_snapshot,
)

logger = logging.getLogger(__name__)


async def compute_cis_snapshots() -> dict[str, Any]:
    """
    For each citizen: CIS for [period_start, period_end) UTC where
    period_end = now, period_start = max(last_global_run, period_end - 7 days) or (now - 7d) if never run.
    Stores IST inclusive dates on snapshots; sets user.last_updated_cis; advances scheduler (+7d next run).
    """
    period_end = datetime.now(timezone.utc)
    n = 0
    meta: dict[str, Any] = {}

    async with AsyncSessionLocal() as db:
        st = await get_cis_scheduler_state(db)
        if st.last_run_at is None:
            period_start = period_end - timedelta(days=7)
        else:
            last = st.last_run_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            else:
                last = last.astimezone(timezone.utc)
            period_start = max(last, period_end - timedelta(days=7))

        week_start_d, week_end_d = ist_inclusive_dates_for_period(period_start, period_end)

        r = await db.execute(select(User).where(User.role == "citizen"))
        users = r.scalars().all()
        for user in users:
            try:
                payload = await calculate_user_cis_for_period(db, user, period_start, period_end)
                await upsert_cis_snapshot(
                    db,
                    user_id=user.id,
                    week_start=week_start_d,
                    week_end=week_end_d,
                    payload=payload,
                )
                user.last_updated_cis = period_end
                user.cis_score = Decimal(str(payload["total_score"]))
                n += 1
            except Exception:
                logger.exception("CIS snapshot failed for user %s", user.id)

        st.last_run_at = period_end
        st.next_run_at = period_end + timedelta(days=7)
        await db.commit()

        meta = {
            "processed": n,
            "week_start": week_start_d.isoformat(),
            "week_end": week_end_d.isoformat(),
            "period_start_ist": format_iso_ist(period_start),
            "period_end_ist": format_iso_ist(period_end - timedelta(microseconds=1))
            if period_end > period_start
            else format_iso_ist(period_start),
            "next_scheduled_run_ist": format_iso_ist(st.next_run_at),
            "next_scheduled_run_display": format_datetime_display_ist(st.next_run_at),
            "timezone": "Asia/Kolkata",
        }

    logger.info(
        "CIS snapshots: processed %s citizens, IST window %s – %s, next run %s",
        n,
        week_start_d,
        week_end_d,
        meta.get("next_scheduled_run_display"),
    )
    return meta


async def maybe_run_scheduled_cis() -> int:
    """
    If now >= next_run_at (or seed next_run_at when unset), run compute_cis_snapshots.
    When next_run_at is null on first deploy, sets next_run = now + 7d without computing.
    """
    async with AsyncSessionLocal() as db:
        st = await get_cis_scheduler_state(db)
        now = datetime.now(timezone.utc)
        if st.next_run_at is None:
            st.next_run_at = now + timedelta(days=7)
            await db.commit()
            logger.info("CIS scheduler: seeded next_run_at = now + 7 days (no snapshot yet)")
            return 0
        nr = st.next_run_at
        if nr.tzinfo is None:
            nr = nr.replace(tzinfo=timezone.utc)
        else:
            nr = nr.astimezone(timezone.utc)
        if now < nr:
            return 0

    out = await compute_cis_snapshots()
    return int(out.get("processed") or 0)
