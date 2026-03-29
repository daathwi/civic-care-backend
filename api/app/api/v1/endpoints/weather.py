"""Ward weather & air quality endpoint. Requires authenticated user with ward."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.models import User, Ward, WorkerProfile
from app.schemas.weather import WardWeatherOut
from app.services.weather_service import fetch_ward_weather

router = APIRouter(prefix="/weather", tags=["weather"])


def _get_user_ward_id(user: User) -> uuid.UUID | None:
    """Resolve ward_id for citizen or staff."""
    if user.ward_id:
        return user.ward_id
    if user.worker_profile and user.worker_profile.ward_id:
        return user.worker_profile.ward_id
    return None


@router.get(
    "/ward",
    response_model=WardWeatherOut,
    summary="Get ward weather and air quality",
    description="Returns weather and air quality for the authenticated user's ward. "
    "Uses ward centroid (lat, lng) to fetch from Open-Meteo. Pass ward_id from login response.",
)
async def get_ward_weather(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    ward_id: uuid.UUID | None = Query(None, description="Ward UUID from login response (optional; falls back to user's ward)."),
):
    resolved_ward_id = ward_id or _get_user_ward_id(user)
    if not resolved_ward_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No ward assigned. Pass ward_id from login response or ensure user has ward.",
        )

    result = await db.execute(
        select(Ward)
        .options(
            selectinload(Ward.zone),
            # Required for _get_ward_out (w.party.name); lazy-load breaks AsyncSession.
            selectinload(Ward.party),
        )
        .where(Ward.id == resolved_ward_id)
    )
    ward = result.scalar_one_or_none()
    if not ward:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ward not found")

    # Get centroid from polygon (computed in wards endpoint helper)
    from app.api.v1.endpoints.wards import _get_ward_out

    ward_out = _get_ward_out(ward, ward.zone.name if ward.zone else None)
    lat = ward_out.centroid_lat
    lng = ward_out.centroid_lng
    # Fallback to Delhi center if ward has no polygon/centroid
    if lat is None or lng is None:
        lat, lng = 28.6139, 77.2090  # Delhi center

    try:
        data = await fetch_ward_weather(lat, lng)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Weather service unavailable: {str(e)}",
        ) from e

    return WardWeatherOut(
        ward_id=str(ward.id),
        ward_name=ward.name,
        air_quality=data["air_quality"],
        weather=data["weather"],
    )
