from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_manager
from app.db.database import get_db
from app.core.security import get_password_hash
from app.models.models import User, WorkerProfile
from app.schemas.worker import WorkerCreate, WorkerListResponse, WorkerOut, WorkerUpdate

# API paths remain /workers for compatibility, but all user-facing text refers to \"Field Assistants\".
router = APIRouter(prefix="/workers", tags=["field assistants"])


def _to_worker_out(user: User) -> WorkerOut:
    wp = user.worker_profile
    role = getattr(user.role, "value", user.role) if hasattr(user.role, "value") else user.role
    return WorkerOut(
        id=user.id,
        name=user.name,
        email=user.email,
        designation=wp.designation_title if wp else "",
        phone=user.phone,
        address=user.address,
        role=role,
        department_id=wp.department_id if wp else None,
        department_name=wp.department.name if wp and wp.department else None,
        zone_id=wp.zone_id if wp else None,
        ward_id=wp.ward_id if wp else None,
        last_active_ward=wp.ward.name if wp and wp.ward else None,
        rating=float(wp.rating) if wp and wp.rating else None,
        tasks_completed=wp.tasks_completed if wp else 0,
        tasks_active=wp.tasks_active if wp else 0,
        status=wp.current_status if wp else None,
    )


@router.get(
    "",
    response_model=WorkerListResponse,
    summary="List field assistants",
    description="Paginated list of field assistants (fieldManager and fieldAssistant). Optional filters: department, ward_id, status. **Access:** public (no auth).",
    response_description="List of field assistants and total count.",
)
async def list_workers(
    db: AsyncSession = Depends(get_db),
    department: uuid.UUID | None = Query(None, description="Filter by department UUID."),
    ward_id: uuid.UUID | None = Query(None, description="Filter by ward UUID."),
    status_filter: str | None = Query(None, alias="status", description="Filter by status: onDuty, offDuty."),
    skip: int = Query(0, ge=0, description="Number of items to skip (offset)."),
    limit: int = Query(50, ge=1, le=100, description="Page size."),
):
    query = (
        select(User)
        .join(WorkerProfile, WorkerProfile.user_id == User.id)
        .options(
            selectinload(User.worker_profile).selectinload(WorkerProfile.department),
            selectinload(User.worker_profile).selectinload(WorkerProfile.ward),
        )
        .where(User.role.in_(["fieldManager", "fieldAssistant"]))
    )
    count_q = (
        select(func.count(User.id))
        .join(WorkerProfile, WorkerProfile.user_id == User.id)
        .where(User.role.in_(["fieldManager", "fieldAssistant"]))
    )

    if department:
        query = query.where(WorkerProfile.department_id == department)
        count_q = count_q.where(WorkerProfile.department_id == department)
    if ward_id:
        query = query.where(WorkerProfile.ward_id == ward_id)
        count_q = count_q.where(WorkerProfile.ward_id == ward_id)
    if status_filter:
        query = query.where(WorkerProfile.current_status == status_filter)
        count_q = count_q.where(WorkerProfile.current_status == status_filter)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.offset(skip).limit(limit))
    workers = result.scalars().unique().all()

    return WorkerListResponse(
        items=[_to_worker_out(w) for w in workers],
        total=total,
    )


@router.get(
    "/{worker_id}",
    response_model=WorkerOut,
    summary="Get field assistant by ID",
    description="Return a single field assistant by UUID. **Access:** public (no auth).",
    response_description="Field assistant detail.",
)
async def get_worker(
    worker_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.worker_profile).selectinload(WorkerProfile.department),
            selectinload(User.worker_profile).selectinload(WorkerProfile.ward),
        )
        .where(User.id == worker_id, User.role.in_(["fieldManager", "fieldAssistant"]))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Field assistant not found")
    return _to_worker_out(user)


@router.post(
    "",
    response_model=WorkerOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create field assistant",
    description="Create a new field assistant (user with role fieldAssistant or fieldManager). **Access:** fieldManager or admin only (Bearer required).",
    response_description="Created field assistant.",
)
async def create_worker(
    body: WorkerCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    existing = await db.execute(select(User).where(User.phone == body.phone))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Phone number already registered")
    if body.role not in ("fieldManager", "fieldAssistant"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "role must be fieldManager or fieldAssistant")

    user = User(
        name=body.name,
        email=body.email,
        phone=body.phone,
        address=body.address,
        password_hash=get_password_hash(body.password),
        role=body.role,
    )
    db.add(user)
    await db.flush()

    profile = WorkerProfile(
        user_id=user.id,
        designation_title=body.designation_title,
        department_id=body.department_id,
        zone_id=body.zone_id,
        ward_id=body.ward_id,
        tasks_completed=0,
        tasks_active=0,
    )
    db.add(profile)
    await db.commit()

    result = await db.execute(
        select(User)
        .options(
            selectinload(User.worker_profile).selectinload(WorkerProfile.department),
            selectinload(User.worker_profile).selectinload(WorkerProfile.ward),
        )
        .where(User.id == user.id)
    )
    return _to_worker_out(result.scalar_one())


@router.patch(
    "/{worker_id}",
    response_model=WorkerOut,
    summary="Update field assistant",
    description="Update a field assistant. **Access:** fieldManager or admin only.",
)
async def update_worker(
    worker_id: uuid.UUID,
    body: WorkerUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.worker_profile).selectinload(WorkerProfile.department),
            selectinload(User.worker_profile).selectinload(WorkerProfile.ward),
        )
        .where(User.id == worker_id, User.role.in_(["fieldManager", "fieldAssistant"]))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Field assistant not found")
    if body.name is not None:
        user.name = body.name
    if body.email is not None:
        user.email = body.email
    if body.phone is not None:
        existing = await db.execute(select(User).where(User.phone == body.phone, User.id != worker_id))
        if existing.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "Phone number already registered")
        user.phone = body.phone
    if body.address is not None:
        user.address = body.address
    if body.password is not None:
        user.password_hash = get_password_hash(body.password)
    if body.role is not None:
        if body.role not in ("fieldManager", "fieldAssistant"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "role must be fieldManager or fieldAssistant")
        user.role = body.role
    wp = user.worker_profile
    if wp:
        if body.designation_title is not None:
            wp.designation_title = body.designation_title
        if body.department_id is not None:
            wp.department_id = body.department_id
        if body.zone_id is not None:
            wp.zone_id = body.zone_id
        if body.ward_id is not None:
            wp.ward_id = body.ward_id
    await db.commit()
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.worker_profile).selectinload(WorkerProfile.department),
            selectinload(User.worker_profile).selectinload(WorkerProfile.ward),
        )
        .where(User.id == worker_id)
    )
    return _to_worker_out(result.scalar_one())


@router.delete(
    "/{worker_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete field assistant",
    description="Delete a field assistant (user and profile). **Access:** fieldManager or admin only.",
)
async def delete_worker(
    worker_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_manager),
):
    result = await db.execute(select(User).where(User.id == worker_id, User.role.in_(["fieldManager", "fieldAssistant"])))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Field assistant not found")
    await db.delete(user)
    await db.commit()
