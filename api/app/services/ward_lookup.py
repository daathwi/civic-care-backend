from typing import Any

from shapely.geometry import shape
from sqlalchemy import select
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
        select(Ward).where(Ward.polygon_geojson.isnot(None))
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
    from shapely.geometry import Point
    
    wards_with_geoms = await _get_ward_geometries(db)
    point = Point(lng, lat)

    for ward, geom in wards_with_geoms:
        if geom.contains(point):
            return ward

    return None
