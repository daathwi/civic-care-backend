from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from shapely.geometry import shape


from app.api.deps import require_manager
from app.db.database import get_db
from app.models.models import Department, GrievanceCategory, PoliticalParty, User, Ward, WorkerProfile, Zone
from app.schemas.ward import (
    CategoryListOut,
    DepartmentCategoryOut,
    GrievanceCategoryCreate,
    GrievanceCategoryUpdate,
    PoliticalPartyCreate,
    PoliticalPartyOut,
    PoliticalPartyUpdate,
    WardCreate,
    WardLookupResult,
    WardOut,
    WardUpdate,
    ZoneCreate,
    ZoneOut,
    ZoneUpdate,
)
from app.schemas.auth import DepartmentCreate, DepartmentOut, DepartmentUpdate
from app.services.ward_lookup import lookup_ward_by_coords

from app.services.ward_lookup import lookup_ward_by_coords
from fastapi.responses import JSONResponse

router = APIRouter(tags=["wards & departments"])

# In-memory cache for GeoJSON
_GEOJSON_CACHE = None


def _get_ward_out(w: Ward, zone_name: str | None = None) -> WardOut:
    """Helper to convert a Ward model to WardOut schema, calculating centroid if available."""
    centroid_lat = None
    centroid_lng = None
    min_lat, max_lat, min_lng, max_lng = None, None, None, None
    if w.polygon_geojson:
        try:
            # Handle if geojson is list (sometimes stored as multi-polygon coordinates)
            geojson = w.polygon_geojson
            if isinstance(geojson, list):
                geojson = {"type": "MultiPolygon", "coordinates": geojson}
            
            geom = shape(geojson)
            if geom and geom.is_valid:
                centroid = geom.centroid
                centroid_lat = centroid.y
                centroid_lng = centroid.x
                
                # Calculate bounds
                bounds = geom.bounds  # (minx, miny, maxx, maxy)
                min_lng, min_lat, max_lng, max_lat = bounds
        except Exception as e:
            print(f"Error calculating geometry for ward {w.number}: {e}")

    party_name = w.party.name if w.party else w.representative_party
    return WardOut(
        id=w.id,
        name=w.name,
        number=w.number,
        zone_id=w.zone_id,
        zone_name=zone_name or (w.zone.name if w.zone else None),
        representative_name=w.representative_name,
        representative_phone=w.representative_phone or [],
        party_id=w.party_id,
        representative_party=party_name,
        representative_email=w.representative_email,
        centroid_lat=centroid_lat,
        centroid_lng=centroid_lng,
        min_lat=min_lat,
        max_lat=max_lat,
        min_lng=min_lng,
        max_lng=max_lng,
    )


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------

@router.get(
    "/zones",
    response_model=list[ZoneOut],
    summary="Browse administrative zones",
    description="See the different zones of the city used for managing departments.",
    operation_id="listAdministrativeZones",
    response_description="List of zones.",
)
async def list_zones(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Zone).order_by(Zone.name))
    return [ZoneOut.model_validate(z) for z in result.scalars().all()]


@router.get(
    "/zones/{zone_id}",
    response_model=ZoneOut,
    summary="View zone details",
    description="See the name and code for a specific administrative zone.",
    operation_id="getZoneDetails",
)
async def get_zone(zone_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    zone = (await db.execute(select(Zone).where(Zone.id == zone_id))).scalar_one_or_none()
    if not zone:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zone not found")
    return ZoneOut.model_validate(zone)


@router.patch(
    "/zones/{zone_id}",
    response_model=ZoneOut,
    summary="Update zone details",
    description="Change the name or code for an existing administrative zone.",
    operation_id="updateZoneDetails",
)
async def update_zone(
    zone_id: uuid.UUID,
    body: ZoneUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    zone = (await db.execute(select(Zone).where(Zone.id == zone_id))).scalar_one_or_none()
    if not zone:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zone not found")
    if body.name is not None:
        zone.name = body.name
    if body.code is not None:
        existing = await db.execute(select(Zone).where(Zone.code == body.code, Zone.id != zone_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "Zone code already exists")
        zone.code = body.code
    await db.commit()
    await db.refresh(zone)
    return ZoneOut.model_validate(zone)


@router.delete(
    "/zones/{zone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a zone",
    description="Delete an administrative zone from the system. It must not have any wards in it.",
    operation_id="deleteAdministrativeZone",
)
async def delete_zone(
    zone_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    zone = (await db.execute(select(Zone).where(Zone.id == zone_id))).scalar_one_or_none()
    if not zone:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zone not found")
    n = (await db.execute(select(func.count(Ward.id)).where(Ward.zone_id == zone_id))).scalar() or 0
    if n > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot delete zone: it has wards. Remove wards first.")
    await db.delete(zone)
    await db.commit()


@router.post(
    "/zones",
    response_model=ZoneOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new zone",
    description="Create a new administrative zone in the city management system.",
    operation_id="createNewAdministrativeZone",
    response_description="Created zone.",
)
async def create_zone(
    body: ZoneCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    existing = await db.execute(select(Zone).where(Zone.code == body.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Zone code already exists")
    zone = Zone(name=body.name, code=body.code)
    db.add(zone)
    await db.commit()
    await db.refresh(zone)
    return ZoneOut.model_validate(zone)


# ---------------------------------------------------------------------------
# Wards
# ---------------------------------------------------------------------------

@router.get(
    "/wards",
    response_model=list[WardOut],
    summary="Browse city wards",
    description="Look through the different wards in the city to find which one you are in.",
    operation_id="listCityWardsOverview",
    response_description="List of wards.",
)
async def list_wards(
    db: AsyncSession = Depends(get_db),
    zone_id: uuid.UUID | None = Query(None, description="Filter by zone UUID."),
):
    query = select(Ward).options(selectinload(Ward.zone), selectinload(Ward.party))
    if zone_id:
        query = query.where(Ward.zone_id == zone_id)
    query = query.order_by(Ward.number)
    result = await db.execute(query)
    wards = result.scalars().all()
    return [_get_ward_out(w) for w in wards]


@router.get(
    "/wards/lookup",
    response_model=WardLookupResult,
    summary="Find your ward automatically",
    description="Use your GPS location to find out which ward and zone you are currently in.",
    operation_id="lookupWardByCoordinates",
    response_description="Ward if found, else found=false.",
)
async def lookup_ward(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    db: AsyncSession = Depends(get_db),
):
    ward = await lookup_ward_by_coords(db, lat, lng)
    if ward:
        zone = None
        if ward.zone_id:
            zone_result = await db.execute(select(Zone).where(Zone.id == ward.zone_id))
            zone = zone_result.scalar_one_or_none()
        return WardLookupResult(
            found=True,
            ward=_get_ward_out(ward, zone_name=zone.name if zone else None)
        )
    return WardLookupResult(found=False)


def _load_ward_geojson() -> dict:
    """Load ward boundaries from GPKG or GeoJSON file. Returns GeoJSON FeatureCollection."""
    global _GEOJSON_CACHE
    if _GEOJSON_CACHE is not None:
        return _GEOJSON_CACHE

    current = Path(__file__).resolve()
    # civic-care-backend/data/delhi_wards.gpkg (parents[5] = civic-care-backend when run from api/)
    gpkg_path = current.parents[5] / "data" / "delhi_wards.gpkg"
    geojson_candidates = [
        current.parents[7] / "backend_tests" / "delhi_wards.geojson",
        current.parents[6] / "backend_tests" / "delhi_wards.geojson",
        current.parents[5] / "data" / "delhi_wards.geojson",
    ]

    # 1. Try GPKG first (primary source)
    if gpkg_path.is_file():
        try:
            import geopandas as gpd

            gdf = gpd.read_file(gpkg_path)
            if gdf.crs and gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs(epsg=4326)
            # Use geopandas __geo_interface__; clean properties for admin map
            raw = gdf.__geo_interface__
            for feat in raw["features"]:
                props = feat.get("properties") or {}
                # Add population alias for admin (expects POPULATION or population)
                if "TotalPop" in props and props["TotalPop"] is not None:
                    try:
                        props["population"] = int(props["TotalPop"])
                    except (TypeError, ValueError):
                        pass
                # Drop NaN/NaT and ensure JSON-serializable values
                def _serialize(v):
                    if v is None or (isinstance(v, float) and v != v):
                        return None
                    if hasattr(v, "isoformat"):
                        return v.isoformat()
                    if hasattr(v, "item"):  # numpy scalar
                        return v.item()
                    return v

                feat["properties"] = {
                    k: _serialize(v)
                    for k, v in props.items()
                    if _serialize(v) is not None
                }
            _GEOJSON_CACHE = raw
            return _GEOJSON_CACHE
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load ward GPKG: {e}",
            ) from e

    # 2. Fallback to GeoJSON files
    for fp in geojson_candidates:
        if fp.is_file():
            with fp.open("r", encoding="utf-8") as f:
                _GEOJSON_CACHE = json.load(f)
                return _GEOJSON_CACHE

    raise HTTPException(status.HTTP_404_NOT_FOUND, "Ward GeoJSON not found (no delhi_wards.gpkg or delhi_wards.geojson)")


@router.get(
    "/wards/geojson",
    summary="View ward boundaries on map",
    description="Get the digital boundaries of all wards to show them on a map.",
    operation_id="fetchWardBoundariesGeoJSON",
)
async def wards_geojson():
    geojson = _load_ward_geojson()
    return JSONResponse(
        content=geojson,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get(
    "/wards/{ward_id}",
    response_model=WardOut,
    summary="View specific ward details",
    description="See name, representative, and location info for a particular ward.",
    operation_id="fetchSpecificWardDetails",
)
async def get_ward(
    ward_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Ward).options(selectinload(Ward.zone), selectinload(Ward.party)).where(Ward.id == ward_id))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ward not found")
    return _get_ward_out(w)


@router.patch(
    "/wards/{ward_id}",
    response_model=WardOut,
    summary="Update ward information",
    description="Change the details of a ward, such as its name or representative.",
    operation_id="modifyWardInformation",
)
async def update_ward(
    ward_id: uuid.UUID,
    body: WardUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    result = await db.execute(select(Ward).options(selectinload(Ward.zone), selectinload(Ward.party)).where(Ward.id == ward_id))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ward not found")
    if body.zone_id is not None:
        z = (await db.execute(select(Zone).where(Zone.id == body.zone_id))).scalar_one_or_none()
        if not z:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Zone not found")
        w.zone_id = body.zone_id
    if body.name is not None:
        w.name = body.name
    if body.number is not None:
        existing = await db.execute(select(Ward).where(Ward.zone_id == w.zone_id, Ward.number == body.number, Ward.id != ward_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "Ward number already exists in this zone")
        w.number = body.number
    if body.representative_name is not None:
        w.representative_name = body.representative_name
    if body.representative_phone is not None:
        w.representative_phone = body.representative_phone
    if "party_id" in body.model_fields_set:
        if body.party_id:
            p = (await db.execute(select(PoliticalParty).where(PoliticalParty.id == body.party_id))).scalar_one_or_none()
            if not p:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Political party not found")
            w.party_id = body.party_id
            w.representative_party = None
        else:
            w.party_id = None
    if "representative_email" in body.model_fields_set:
        w.representative_email = body.representative_email
    await db.commit()
    await db.refresh(w)
    result = await db.execute(select(Ward).options(selectinload(Ward.zone), selectinload(Ward.party)).where(Ward.id == ward_id))
    w = result.scalar_one()
    return _get_ward_out(w)


@router.delete(
    "/wards/{ward_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a ward",
    description="Delete a ward from the city records.",
    operation_id="deleteCityWard",
)
async def delete_ward(
    ward_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    w = (await db.execute(select(Ward).where(Ward.id == ward_id))).scalar_one_or_none()
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ward not found")
    await db.delete(w)
    await db.commit()


@router.post(
    "/wards",
    response_model=WardOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ward",
    description="Add a new ward to a specific administrative zone.",
    operation_id="addNewCityWardRecord",
    response_description="Created ward.",
)
async def create_ward(
    body: WardCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    zone_result = await db.execute(select(Zone).where(Zone.id == body.zone_id))
    if not zone_result.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zone not found")
    existing = await db.execute(
        select(Ward).where(Ward.zone_id == body.zone_id, Ward.number == body.number)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ward number already exists in this zone")
    if body.party_id:
        p = (await db.execute(select(PoliticalParty).where(PoliticalParty.id == body.party_id))).scalar_one_or_none()
        if not p:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Political party not found")
    ward = Ward(
        zone_id=body.zone_id,
        name=body.name,
        number=body.number,
        representative_name=body.representative_name,
        representative_phone=body.representative_phone or None,
        party_id=body.party_id,
        representative_email=body.representative_email,
    )
    db.add(ward)
    await db.commit()
    await db.refresh(ward)
    result = await db.execute(select(Ward).options(selectinload(Ward.zone), selectinload(Ward.party)).where(Ward.id == ward.id))
    w = result.scalar_one()
    return _get_ward_out(w)


# ---------------------------------------------------------------------------
# Political Parties
# ---------------------------------------------------------------------------

@router.get(
    "/parties",
    response_model=list[PoliticalPartyOut],
    summary="Browse political parties",
    description="List all political parties for ward analytics.",
    operation_id="listPoliticalParties",
)
async def list_parties(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PoliticalParty).order_by(PoliticalParty.name))
    return [PoliticalPartyOut.model_validate(p) for p in result.scalars().all()]


@router.post(
    "/parties",
    response_model=PoliticalPartyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create political party",
    description="Add a new political party.",
    operation_id="createPoliticalParty",
)
async def create_party(
    body: PoliticalPartyCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    party = PoliticalParty(
        name=body.name,
        short_code=body.short_code,
        color=body.color,
    )
    db.add(party)
    await db.commit()
    await db.refresh(party)
    return PoliticalPartyOut.model_validate(party)


@router.get(
    "/parties/analytics/grievances",
    summary="Grievance stats by political party",
    description="Count of grievances by status per party (for charts and dashboards).",
    operation_id="getPartyGrievanceAnalytics",
)
async def party_grievance_analytics(db: AsyncSession = Depends(get_db)):
    from app.models.models import Grievance

    stmt = (
        select(
            PoliticalParty.id,
            PoliticalParty.name,
            PoliticalParty.short_code,
            PoliticalParty.color,
            Grievance.status,
            func.count(Grievance.id).label("count"),
        )
        .select_from(PoliticalParty)
        .join(Ward, Ward.party_id == PoliticalParty.id)
        .join(Grievance, Grievance.ward_id == Ward.id)
        .group_by(PoliticalParty.id, PoliticalParty.name, PoliticalParty.short_code, PoliticalParty.color, Grievance.status)
    )
    result = await db.execute(stmt)
    rows = result.all()
    by_party: dict[uuid.UUID, dict] = {}
    for r in rows:
        pid = r[0]
        if pid not in by_party:
            by_party[pid] = {
                "party_id": str(pid),
                "party_name": r[1],
                "short_code": r[2],
                "color": r[3],
                "escalated": 0,
                "pending": 0,
                "assigned": 0,
                "inprogress": 0,
                "resolved": 0,
                "total": 0,
            }
        status_val = (r[4] or "pending").lower()
        count = r[5] or 0
        if status_val in by_party[pid]:
            by_party[pid][status_val] = count
        by_party[pid]["total"] += count
    return list(by_party.values())


@router.get(
    "/parties/{party_id}",
    response_model=PoliticalPartyOut,
    summary="View party details",
    operation_id="getPoliticalParty",
)
async def get_party(party_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(PoliticalParty).where(PoliticalParty.id == party_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Political party not found")
    return PoliticalPartyOut.model_validate(p)


@router.patch(
    "/parties/{party_id}",
    response_model=PoliticalPartyOut,
    summary="Update political party",
    operation_id="updatePoliticalParty",
)
async def update_party(
    party_id: uuid.UUID,
    body: PoliticalPartyUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    p = (await db.execute(select(PoliticalParty).where(PoliticalParty.id == party_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Political party not found")
    if body.name is not None:
        p.name = body.name
    if body.short_code is not None:
        p.short_code = body.short_code
    if body.color is not None:
        p.color = body.color
    await db.commit()
    await db.refresh(p)
    return PoliticalPartyOut.model_validate(p)


@router.delete(
    "/parties/{party_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete political party",
    operation_id="deletePoliticalParty",
)
async def delete_party(
    party_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    p = (await db.execute(select(PoliticalParty).where(PoliticalParty.id == party_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Political party not found")
    await db.delete(p)
    await db.commit()


# ---------------------------------------------------------------------------
# Departments & Categories
# ---------------------------------------------------------------------------

@router.get(
    "/departments",
    response_model=list[DepartmentOut],
    summary="Browse city departments",
    description="See a list of all official departments that help maintain the city.",
    operation_id="listOfficialDepartments",
    response_description="List of departments.",
)
async def list_departments(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Department).order_by(Department.name))
    return [DepartmentOut.model_validate(d) for d in result.scalars().all()]


@router.get(
    "/departments/{dept_id}",
    response_model=DepartmentOut,
    summary="View department details",
    description="See detailed info about a specific city department, like its role and manager title.",
    operation_id="fetchDepartmentSpecificDetails",
)
async def get_department(dept_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    dept = (await db.execute(select(Department).where(Department.id == dept_id))).scalar_one_or_none()
    if not dept:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    return DepartmentOut.model_validate(dept)


@router.patch(
    "/departments/{dept_id}",
    response_model=DepartmentOut,
    summary="Update department details",
    description="Modify a department's information, like its colors or contact tags.",
    operation_id="updateDepartmentConfiguration",
)
async def update_department(
    dept_id: uuid.UUID,
    body: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    dept = (await db.execute(select(Department).where(Department.id == dept_id))).scalar_one_or_none()
    if not dept:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    if body.name is not None:
        dept.name = body.name
    if body.short_code is not None:
        existing = await db.execute(select(Department).where(Department.short_code == body.short_code, Department.id != dept_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "Department short code already exists")
        dept.short_code = body.short_code
    if body.primary_color is not None:
        dept.primary_color = body.primary_color
    if body.icon is not None:
        dept.icon = body.icon
    if body.manager_title is not None:
        dept.manager_title = body.manager_title
    if body.assistant_title is not None:
        dept.assistant_title = body.assistant_title
    if body.jurisdiction_label is not None:
        dept.jurisdiction_label = body.jurisdiction_label
    if body.sdg is not None:
        dept.sdg = body.sdg
    if body.description is not None:
        dept.description = body.description
    await db.commit()
    await db.refresh(dept)
    return DepartmentOut.model_validate(dept)


@router.delete(
    "/departments/{dept_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a department",
    description="Delete a department record. Only possible if no categories or staff are linked to it.",
    operation_id="discardDepartmentRecord",
)
async def delete_department(
    dept_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    dept = (await db.execute(select(Department).where(Department.id == dept_id))).scalar_one_or_none()
    if not dept:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    n_cats = (await db.execute(select(func.count(GrievanceCategory.id)).where(GrievanceCategory.dept_id == dept_id))).scalar() or 0
    if n_cats > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot delete department: it has categories. Remove categories first.")
    n_workers = (await db.execute(select(func.count(WorkerProfile.user_id)).where(WorkerProfile.department_id == dept_id))).scalar() or 0
    if n_workers > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot delete department: it has field assistants. Reassign field assistants first.")
    await db.delete(dept)
    await db.commit()


@router.post(
    "/departments",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new department",
    description="Add a new official department to the city management system.",
    operation_id="registerNewOfficialDepartment",
    response_description="Created department.",
)
async def create_department(
    body: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    existing = await db.execute(select(Department).where(Department.short_code == body.short_code))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Department short code already exists")
    dept = Department(
        name=body.name,
        short_code=body.short_code,
        primary_color=body.primary_color,
        icon=body.icon,
        manager_title=body.manager_title,
        assistant_title=body.assistant_title,
        jurisdiction_label=body.jurisdiction_label,
        sdg=body.sdg,
        description=body.description,
    )
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return DepartmentOut.model_validate(dept)


@router.get(
    "/departments/{dept_id}/categories",
    response_model=list[DepartmentCategoryOut],
    summary="Browse issue categories by department",
    description="See the types of issues a specific department handles.",
    operation_id="listGrievanceCategoriesByDept",
    response_description="List of categories.",
)
async def list_categories(dept_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GrievanceCategory).where(GrievanceCategory.dept_id == dept_id)
    )
    return [DepartmentCategoryOut.model_validate(c) for c in result.scalars().all()]


@router.post(
    "/departments/{dept_id}/categories",
    response_model=DepartmentCategoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new issue category",
    description="Create a new type of issue that citizens can report to a department.",
    operation_id="createNewGrievanceCategory",
    response_description="Created category.",
)
async def create_category(
    dept_id: uuid.UUID,
    body: GrievanceCategoryCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    dept = (await db.execute(select(Department).where(Department.id == dept_id))).scalar_one_or_none()
    if not dept:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    cat = GrievanceCategory(dept_id=dept_id, name=body.name)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return DepartmentCategoryOut.model_validate(cat)


@router.get(
    "/categories",
    response_model=list[CategoryListOut],
    summary="View all issue types",
    description="See every type of issue that can be reported across all departments.",
    operation_id="listAllReportableCategories",
    response_description="List of categories with dept_name.",
)
async def list_all_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GrievanceCategory, Department.name)
        .join(Department, GrievanceCategory.dept_id == Department.id)
        .order_by(Department.name, GrievanceCategory.name)
    )
    return [
        CategoryListOut(id=c.id, name=c.name, dept_id=c.dept_id, dept_name=dept_name)
        for c, dept_name in result.all()
    ]


@router.get(
    "/categories/{cat_id}",
    response_model=DepartmentCategoryOut,
    summary="See specific category details",
    description="Get detailed info about a single issue category.",
    operation_id="fetchGrievanceCategoryDetails",
)
async def get_category(cat_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cat = (await db.execute(select(GrievanceCategory).where(GrievanceCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return DepartmentCategoryOut.model_validate(cat)


@router.patch(
    "/categories/{cat_id}",
    response_model=DepartmentCategoryOut,
    summary="Modify issue category",
    description="Rename or update an existing issue category.",
    operation_id="updateGrievanceCategoryName",
)
async def update_category(
    cat_id: uuid.UUID,
    body: GrievanceCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    cat = (await db.execute(select(GrievanceCategory).where(GrievanceCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    if body.name is not None:
        cat.name = body.name
    await db.commit()
    await db.refresh(cat)
    return DepartmentCategoryOut.model_validate(cat)


@router.delete(
    "/categories/{cat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an issue category",
    description="Delete a category from the list of reportable issues.",
    operation_id="removeGrievanceCategory",
)
async def delete_category(
    cat_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    cat = (await db.execute(select(GrievanceCategory).where(GrievanceCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    await db.delete(cat)
    await db.commit()
