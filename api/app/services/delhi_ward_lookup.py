"""
Ward lookup from Delhi wards GeoPackage (delhi_wards.gpkg).
Loads the file once and uses a spatial index for fast point-in-polygon.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import settings

_WARDS_GDF = None
_SINDEX = None


def _load_gpkg() -> tuple[Any, Any] | None:
    global _WARDS_GDF, _SINDEX
    if _WARDS_GDF is not None:
        return _WARDS_GDF, _SINDEX
    path = settings.delhi_wards_gpkg_path
    if not path or not path.exists():
        return None
    try:
        import geopandas as gpd

        _WARDS_GDF = gpd.read_file(path)
        _SINDEX = _WARDS_GDF.sindex
        return _WARDS_GDF, _SINDEX
    except Exception:
        return None


def get_ward_from_location(lat: float, lon: float) -> dict[str, Any] | None:
    """
    Return ward and zone info for a point (lat, lon) or None if not found / gpkg not loaded.
    Keys: WardName, Ward_No, AC_Name; ward_display; zone_display (from AC_Name or Zone column if present).
    """
    loaded = _load_gpkg()
    if loaded is None:
        return None
    gdf, sindex = loaded
    from shapely.geometry import Point

    point = Point(lon, lat)
    try:
        possible = list(sindex.intersection(point.bounds))
        candidates = gdf.iloc[possible]
        match = candidates[candidates.contains(point)]
        if match.empty:
            return None
        row = match.iloc[0]
        ward_name = row.get("WardName")
        ward_no = row.get("Ward_No")
        ac = row.get("AC_Name")
        ward_display = f"Ward {ward_no}" if ward_no is not None else (ward_name or "Unknown")
        # Zone: use Zone/ZoneName/Zone_Name if present in gpkg, else AC_Name as area/zone
        zone_display = (
            row.get("Zone") or row.get("ZoneName") or row.get("Zone_Name")
            or (str(ac) if ac is not None and str(ac).strip() else None)
        )
        return {
            "WardName": ward_name,
            "Ward_No": ward_no,
            "AC_Name": ac,
            "ward_display": ward_display,
            "zone_display": zone_display,
        }
    except Exception:
        return None
