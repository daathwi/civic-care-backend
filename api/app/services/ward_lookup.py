from typing import Any

from shapely.geometry import Point, shape
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Ward
# In-memory cache for ward geometries
# List of (WardObject, ShapelyGeometry)
_WARD_GEOMETRY_CACHE: list[tuple[Ward, Any]] | None = None


async def _get_ward_geometries(db: AsyncSession) -> list[tuple[Ward, Any]]:
    """Load and parse all ward geometries into memory."""
    global _WARD_GEOMETRY_CACHE
    if _WARD_GEOMETRY_CACHE is not None:
        return _WARD_GEOMETRY_CACHE

    result = await db.execute(
        select(Ward)
        .options(selectinload(Ward.party))
        .where(Ward.polygon_geojson.isnot(None))
    )
    wards = result.scalars().all()
    
    cache = []
    for ward in wards:
        try:
            # The database might store MultiPolygon coordinates directly; wrap if needed
            geojson = ward.polygon_geojson
            if isinstance(geojson, list):
                # Assuming raw coordinates were stored by init_db.py
                geojson = {"type": "MultiPolygon", "coordinates": geojson}
            
            geom = shape(geojson)
            if geom and geom.is_valid:
                cache.append((ward, geom))
            else:
                print(f"Warning: Ward {ward.number} ({ward.name}) has invalid geometry.")
        except Exception as e:
            print(f"Error parsing geometry for ward {ward.number}: {e}")
            continue
    
    _WARD_GEOMETRY_CACHE = cache
    return cache


async def lookup_ward_by_coords(
    db: AsyncSession, lat: float, lng: float,
) -> Ward | None:
    """Point-in-polygon lookup using in-memory Shapely cache."""
    wards_with_geoms = await _get_ward_geometries(db)
    point = Point(lng, lat)

    for ward, geom in wards_with_geoms:
        if geom.contains(point):
            return ward

    return None


# ~35–40 m at Delhi lat; expands ward polygon slightly so GPS drift at edges still counts as inside.
WARD_ATTENDANCE_BUFFER_DEG = 0.00035


async def lookup_ward_for_attendance(
    db: AsyncSession,
    lat: float,
    lng: float,
) -> Ward | None:
    """
    Resolve which Delhi ward contains this GPS point for attendance.

    Uses a small buffer around ward polygons so clock-in/out near boundaries is not rejected
    due to typical GPS error. Falls back to strict contains if buffering fails.
    """
    wards_with_geoms = await _get_ward_geometries(db)
    point = Point(lng, lat)

    for ward, geom in wards_with_geoms:
        try:
            inflated = geom.buffer(WARD_ATTENDANCE_BUFFER_DEG)
            if inflated.covers(point):
                return ward
        except Exception:
            if geom.covers(point):
                return ward

    return None


def invalidate_ward_geometry_cache() -> None:
    """Clear cached ward polygons (e.g. after bulk ward import)."""
    global _WARD_GEOMETRY_CACHE
    _WARD_GEOMETRY_CACHE = None
