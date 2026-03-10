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
from app.models.models import Department, GrievanceCategory, User, Ward, WorkerProfile, Zone
from app.schemas.ward import (
    CategoryListOut,
    DepartmentCategoryOut,
    GrievanceCategoryCreate,
    GrievanceCategoryUpdate,
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

    return WardOut(
        id=w.id,
        name=w.name,
        number=w.number,
        zone_id=w.zone_id,
        zone_name=zone_name or (w.zone.name if w.zone else None),
        representative_name=w.representative_name,
        representative_phone=w.representative_phone or [],
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
    summary="List zones",
    description="List all zones. **Access:** public (no auth).",
    response_description="List of zones.",
)
async def list_zones(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Zone).order_by(Zone.name))
    return [ZoneOut.model_validate(z) for z in result.scalars().all()]


@router.get(
    "/zones/{zone_id}",
    response_model=ZoneOut,
    summary="Get zone by ID",
    description="Return a single zone. **Access:** public (no auth).",
)
async def get_zone(zone_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    zone = (await db.execute(select(Zone).where(Zone.id == zone_id))).scalar_one_or_none()
    if not zone:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Zone not found")
    return ZoneOut.model_validate(zone)


@router.patch(
    "/zones/{zone_id}",
    response_model=ZoneOut,
    summary="Update zone",
    description="Update a zone. **Access:** fieldManager or admin only.",
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
    summary="Delete zone",
    description="Delete a zone. Fails if it has wards. **Access:** fieldManager or admin only.",
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
    summary="Create zone",
    description="Create a new zone. **Access:** fieldManager or admin only (Bearer required).",
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
    summary="List wards",
    description="List all wards. Optional filter: zone_id. **Access:** public (no auth).",
    response_description="List of wards.",
)
async def list_wards(
    db: AsyncSession = Depends(get_db),
    zone_id: uuid.UUID | None = Query(None, description="Filter by zone UUID."),
):
    query = select(Ward).options(selectinload(Ward.zone))
    if zone_id:
        query = query.where(Ward.zone_id == zone_id)
    query = query.order_by(Ward.number)
    result = await db.execute(query)
    wards = result.scalars().all()
    return [_get_ward_out(w) for w in wards]


@router.get(
    "/wards/lookup",
    response_model=WardLookupResult,
    summary="Lookup ward by coordinates",
    description="Return the ward that contains the given lat/lng (point-in-polygon). **Access:** public (no auth).",
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


@router.get(
    "/wards/geojson",
    summary="Delhi ward boundaries GeoJSON",
    description="Return Delhi wards boundary polygons as GeoJSON for admin map rendering. **Access:** public (no auth).",
)
async def wards_geojson():
    global _GEOJSON_CACHE
    if _GEOJSON_CACHE is not None:
        return JSONResponse(
            content=_GEOJSON_CACHE,
            headers={"Cache-Control": "public, max-age=86400"},
        )

    current = Path(__file__).resolve()
    candidates = [
        current.parents[7] / "backend_tests" / "delhi_wards.geojson",
        current.parents[6] / "backend_tests" / "delhi_wards.geojson",
    ]
    for fp in candidates:
        if fp.is_file():
            with fp.open("r", encoding="utf-8") as f:
                _GEOJSON_CACHE = json.load(f)
                return JSONResponse(
                    content=_GEOJSON_CACHE,
                    headers={"Cache-Control": "public, max-age=86400"},
                )
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Ward GeoJSON not found")


@router.get(
    "/wards/{ward_id}",
    response_model=WardOut,
    summary="Get ward by ID",
    description="Return a single ward. **Access:** public (no auth).",
)
async def get_ward(
    ward_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Ward).options(selectinload(Ward.zone)).where(Ward.id == ward_id))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ward not found")
    return _get_ward_out(w)


@router.patch(
    "/wards/{ward_id}",
    response_model=WardOut,
    summary="Update ward",
    description="Update a ward. **Access:** fieldManager or admin only.",
)
async def update_ward(
    ward_id: uuid.UUID,
    body: WardUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    result = await db.execute(select(Ward).options(selectinload(Ward.zone)).where(Ward.id == ward_id))
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
    await db.commit()
    await db.refresh(w)
    result = await db.execute(select(Ward).options(selectinload(Ward.zone)).where(Ward.id == ward_id))
    w = result.scalar_one()
    return _get_ward_out(w)


@router.delete(
    "/wards/{ward_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete ward",
    description="Delete a ward. Grievances/field assistants referencing it will have ward_id set to NULL. **Access:** fieldManager or admin only.",
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
    summary="Create ward",
    description="Create a new ward under a zone. **Access:** fieldManager or admin only (Bearer required).",
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
    ward = Ward(
        zone_id=body.zone_id,
        name=body.name,
        number=body.number,
        representative_name=body.representative_name,
        representative_phone=body.representative_phone or None,
    )
    db.add(ward)
    await db.commit()
    await db.refresh(ward)
    result = await db.execute(select(Ward).options(selectinload(Ward.zone)).where(Ward.id == ward.id))
    w = result.scalar_one()
    return _get_ward_out(w)


# ---------------------------------------------------------------------------
# Departments & Categories
# ---------------------------------------------------------------------------

@router.get(
    "/departments",
    response_model=list[DepartmentOut],
    summary="List departments",
    description="List all departments. **Access:** public (no auth).",
    response_description="List of departments.",
)
async def list_departments(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Department).order_by(Department.name))
    return [DepartmentOut.model_validate(d) for d in result.scalars().all()]


@router.get(
    "/departments/{dept_id}",
    response_model=DepartmentOut,
    summary="Get department by ID",
    description="Return a single department. **Access:** public (no auth).",
)
async def get_department(dept_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    dept = (await db.execute(select(Department).where(Department.id == dept_id))).scalar_one_or_none()
    if not dept:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    return DepartmentOut.model_validate(dept)


@router.patch(
    "/departments/{dept_id}",
    response_model=DepartmentOut,
    summary="Update department",
    description="Update a department. **Access:** fieldManager or admin only.",
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
    await db.commit()
    await db.refresh(dept)
    return DepartmentOut.model_validate(dept)


@router.delete(
    "/departments/{dept_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete department",
    description="Delete a department. Fails if it has categories or field assistants. **Access:** fieldManager or admin only.",
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
    summary="Create department",
    description="Create a new department. **Access:** fieldManager or admin only (Bearer required).",
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
    )
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return DepartmentOut.model_validate(dept)


@router.get(
    "/departments/{dept_id}/categories",
    response_model=list[DepartmentCategoryOut],
    summary="List categories by department",
    description="List grievance categories for a department. **Access:** public (no auth).",
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
    summary="Create grievance category",
    description="Create a grievance category under a department. **Access:** fieldManager or admin only (Bearer required).",
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
    summary="List all categories",
    description="List all grievance categories with department name (for admin listing). **Access:** public (no auth).",
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
    summary="Get category by ID",
    description="Return a single grievance category. **Access:** public (no auth).",
)
async def get_category(cat_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cat = (await db.execute(select(GrievanceCategory).where(GrievanceCategory.id == cat_id))).scalar_one_or_none()
    if not cat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return DepartmentCategoryOut.model_validate(cat)


@router.patch(
    "/categories/{cat_id}",
    response_model=DepartmentCategoryOut,
    summary="Update category",
    description="Update a grievance category. **Access:** fieldManager or admin only.",
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
    summary="Delete category",
    description="Delete a category. Grievances referencing it will have category_id set to NULL. **Access:** fieldManager or admin only.",
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
