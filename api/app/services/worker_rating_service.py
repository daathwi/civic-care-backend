"""
Worker rating from citizen grievance ratings.

worker_rating = sum(ratings) / count of ratings for that worker.

Uses grievance_resolution_ratings table: one row per citizen rating event.
Handles reopen: when a grievance is reopened and another worker resolves,
each worker gets their own rating row (e.g. Worker1 gets 2/5, Worker2 gets 4/5).
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import GrievanceResolutionRating, WorkerProfile


async def recalculate_worker_rating(
    db: AsyncSession,
    worker_id: uuid.UUID | None = None,
) -> None:
    """
    Recalculate worker rating from grievance_resolution_ratings.

    worker_rating = sum(ratings) / count
    Updates worker_profile.rating and worker_profile.ratings_count.
    """
    agg = (
        select(
            GrievanceResolutionRating.worker_id,
            func.avg(GrievanceResolutionRating.rating).label("avg_rating"),
            func.count(GrievanceResolutionRating.id).label("ratings_count"),
        )
        .group_by(GrievanceResolutionRating.worker_id)
    )
    if worker_id:
        agg = agg.where(GrievanceResolutionRating.worker_id == worker_id)

    result = await db.execute(agg)
    rows = result.all()

    for row in rows:
        w_id = row.worker_id
        avg_val = float(row.avg_rating) if row.avg_rating is not None else 0.0
        count_val = row.ratings_count or 0

        wp_result = await db.execute(
            select(WorkerProfile).where(WorkerProfile.user_id == w_id)
        )
        wp = wp_result.scalar_one_or_none()
        if wp:
            wp.rating = round(avg_val, 2)
            wp.ratings_count = count_val

    # Reset rating for workers not in the result (no rated grievances)
    if worker_id:
        wp_result = await db.execute(
            select(WorkerProfile).where(WorkerProfile.user_id == worker_id)
        )
        wp = wp_result.scalar_one_or_none()
        if wp and not any(r.worker_id == worker_id for r in rows):
            wp.rating = 0.00
            wp.ratings_count = 0
    else:
        # For full recalc: workers with no ratings get 0
        all_rated_ids = {r.worker_id for r in rows}
        all_wps = await db.execute(select(WorkerProfile))
        for wp in all_wps.scalars().all():
            if wp.user_id not in all_rated_ids:
                wp.rating = 0.00
                wp.ratings_count = 0
