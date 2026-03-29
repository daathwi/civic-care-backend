"""Validate clock-in / clock-out GPS against Delhi ward boundaries."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User
from app.services.ward_lookup import lookup_ward_for_attendance


def _role_str(user: User) -> str:
    r = getattr(user, "role", None)
    if r is None:
        return ""
    return getattr(r, "value", r) if hasattr(r, "value") else str(r)


async def assert_clock_location_within_ward_boundaries(
    db: AsyncSession,
    user: User,
    lat: float,
    lng: float,
) -> None:
    """
    Require GPS to fall inside a Delhi ward polygon (from DB GeoJSON).

    If the user has an assigned ward (worker_profile.ward_id or user.ward_id),
    the point must resolve to that ward (admins are only checked against any ward).
    """
    ward = await lookup_ward_for_attendance(db, lat, lng)
    if ward is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                "Location must be within a Delhi ward boundary. "
                "Enable GPS, wait for a fix, and try again when you are on site."
            ),
        )

    role = _role_str(user)
    if role == "admin":
        return

    assigned: uuid.UUID | None = None
    if user.worker_profile is not None and user.worker_profile.ward_id is not None:
        assigned = user.worker_profile.ward_id
    elif user.ward_id is not None:
        assigned = user.ward_id

    if assigned is None:
        return

    if ward.id != assigned:
        aw = (
            user.worker_profile.ward
            if user.worker_profile is not None
            else None
        )
        assigned_name = getattr(aw, "name", None) or "your assigned ward"
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"You must clock in/out within {assigned_name}. "
                f"Your current location appears to be in {ward.name}. "
                "Move into your assigned ward or contact your supervisor."
            ),
        )
