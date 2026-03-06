from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_can_update_grievance, require_manager
from app.db.database import get_db
from app.services.delhi_ward_lookup import get_ward_from_location
from app.services.ward_lookup import lookup_ward_by_coords
from app.models.models import (
    Assignment, AuditLog, Grievance, GrievanceCategory,
    GrievanceComment, GrievanceMedia, GrievanceVote,
    User, Ward, WorkerProfile,
)
from app.schemas.grievance import (
    AssignWorkerRequest, AssignmentOut, AuditLogOut,
    CommentCreate, CommentOut, GrievanceCreate, GrievanceDetail,
    GrievanceListItem, GrievanceUpdate, MediaOut,
    PaginatedGrievances, VoteRequest,
)
from app.api.v1.endpoints.chat import broadcast_comment

router = APIRouter(prefix="/grievances", tags=["grievances"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Icon names for audit log events; must match Flutter iconFromApi() in grievance_mappers.dart.
def _audit_icon_for_event(title: str | None = None, status: str | None = None) -> str:
    """Return the icon_name to store for an audit log entry. Used whenever any role writes an AuditLog."""
    t = (title or "").strip().lower()
    s = (status or "").strip().lower()
    if "registered" in t or "created" in t or "complaint" in t:
        return "article_outlined"
    if "assigned" in t or "assignment" in t:
        return "assignment_ind_rounded"
    if s == "resolved" or "resolved" in t or "completed" in t:
        return "check_circle_outline_rounded"
    if s == "inprogress" or "in progress" in t or "ongoing" in t:
        return "update_rounded"
    if s == "pending" or "pending" in t:
        return "schedule_rounded"
    if s == "assigned":
        return "assignment_ind_rounded"
    # Default for generic "Updated" or unknown
    return "update_rounded"


def _to_list_item(g: Grievance) -> GrievanceListItem:
    active = next(
        (a for a in (g.assignments or []) if a.status != "completed"),
        None,
    )
    first_image = next(
        (m.media_url for m in (g.media or []) if m.type == "image" and not m.is_resolution_proof),
        None,
    )
    first_audio = next(
        (m.media_url for m in (g.media or []) if m.type == "audio"),
        None,
    )
    return GrievanceListItem(
        id=g.id,
        title=g.title,
        description=g.description,
        lat=g.lat,
        lng=g.lng,
        address=g.address,
        status=g.status,
        priority=g.priority,
        category_name=g.category.name if g.category else None,
        category_dept_id=g.category.dept_id if g.category else None,
        ward_name=g.ward.name if g.ward else None,
        ward_number=g.ward.number if g.ward else None,
        reporter_name=g.reporter.name if g.reporter else None,
        upvotes_count=g.upvotes_count,
        downvotes_count=g.downvotes_count,
        created_at=g.created_at,
        image_url=first_image,
        audio_url=first_audio,
        is_sensitive=g.is_sensitive,
        assigned_to_name=active.assigned_to.name if active and active.assigned_to else None,
        assigned_to_id=active.assigned_to_id if active else None,
    )


def _to_detail(g: Grievance) -> GrievanceDetail:
    active = next(
        (a for a in (g.assignments or []) if a.status != "completed"),
        None,
    )
    first_image = next(
        (m.media_url for m in (g.media or []) if m.type == "image" and not m.is_resolution_proof),
        None,
    )
    resolution_img = next(
        (m.media_url for m in (g.media or []) if m.is_resolution_proof),
        None,
    )
    comments_out = [
        CommentOut(
            id=c.id, user_id=c.user_id,
            user_name=c.user.name if c.user else None,
            text=c.text, created_at=c.created_at,
        )
        for c in (g.comments or [])
    ]
    events_out = [
        AuditLogOut(
            id=e.id, title=e.title, description=e.description,
            icon_name=e.icon_name, created_at=e.created_at,
        )
        for e in (g.audit_logs or [])
    ]
    media_out = [MediaOut.model_validate(m) for m in (g.media or [])]
    assignments_out = [
        AssignmentOut(
            id=a.id,
            assigned_to_id=a.assigned_to_id,
            assigned_to_name=a.assigned_to.name if a.assigned_to else None,
            assigned_to_phone=a.assigned_to.phone if a.assigned_to else None,
            assigned_by_id=a.assigned_by_id,
            status=a.status,
            assigned_at=a.assigned_at,
            completed_at=a.completed_at,
        )
        for a in (g.assignments or [])
    ]

    return GrievanceDetail(
        id=g.id,
        title=g.title,
        description=g.description,
        lat=g.lat,
        lng=g.lng,
        address=g.address,
        status=g.status,
        priority=g.priority,
        category_name=g.category.name if g.category else None,
        category_dept_id=g.category.dept_id if g.category else None,
        ward_name=g.ward.name if g.ward else None,
        ward_number=g.ward.number if g.ward else None,
        reporter_id=g.reporter_id,
        reporter_name=g.reporter.name if g.reporter else None,
        upvotes_count=g.upvotes_count,
        downvotes_count=g.downvotes_count,
        created_at=g.created_at,
        image_url=first_image,
        is_sensitive=g.is_sensitive,
        assigned_to_name=active.assigned_to.name if active and active.assigned_to else None,
        assigned_to_id=active.assigned_to_id if active else None,
        worker_contact=active.assigned_to.phone if active and active.assigned_to else None,
        resolution_image_url=resolution_img,
        resolution_media_url=resolution_img,
        comments=comments_out,
        events=events_out,
        media=media_out,
        assignments=assignments_out,
    )


_GRIEVANCE_LOAD_OPTIONS = [
    selectinload(Grievance.category),
    selectinload(Grievance.ward),
    selectinload(Grievance.reporter),
    selectinload(Grievance.media),
    selectinload(Grievance.assignments).selectinload(Assignment.assigned_to),
]

_GRIEVANCE_DETAIL_OPTIONS = [
    *_GRIEVANCE_LOAD_OPTIONS,
    selectinload(Grievance.comments).selectinload(GrievanceComment.user),
    selectinload(Grievance.audit_logs),
]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=PaginatedGrievances,
    summary="List grievances",
    description="Paginated list of grievances. Optional filters: ward_id, ward_name, status, priority, category_dept, reporter_id. **Access:** public (no auth).",
    response_description="Paginated list of grievance items and total count.",
)
async def list_grievances(
    db: AsyncSession = Depends(get_db),
    ward_id: uuid.UUID | None = Query(None, description="Filter by ward UUID."),
    ward_name: str | None = Query(None, description="Filter by ward name (partial match)."),
    status: str | None = Query(None, description="Filter by status: pending, assigned, inprogress, resolved."),
    priority: str | None = Query(None, description="Filter by priority: low, medium, high."),
    category_dept: uuid.UUID | None = Query(None, description="Filter by category's department UUID."),
    reporter_id: uuid.UUID | None = Query(None, description="Filter by reporter user UUID."),
    skip: int = Query(0, ge=0, description="Number of items to skip (offset)."),
    limit: int = Query(10, ge=1, le=100, description="Page size (default 10)."),
):
    query = select(Grievance).options(*_GRIEVANCE_LOAD_OPTIONS)
    count_query = select(func.count(Grievance.id))

    if ward_id:
        query = query.where(Grievance.ward_id == ward_id)
        count_query = count_query.where(Grievance.ward_id == ward_id)
    if ward_name:
        query = query.join(Grievance.ward).where(Ward.name.ilike(f"%{ward_name}%"))
        count_query = count_query.join(Grievance.ward).where(Ward.name.ilike(f"%{ward_name}%"))
    if status:
        query = query.where(Grievance.status == status)
        count_query = count_query.where(Grievance.status == status)
    if priority:
        query = query.where(Grievance.priority == priority)
        count_query = count_query.where(Grievance.priority == priority)
    if category_dept:
        query = (
            query.join(Grievance.category)
            .where(GrievanceCategory.dept_id == category_dept)
        )
        count_query = (
            count_query.join(Grievance.category)
            .where(GrievanceCategory.dept_id == category_dept)
        )
    if reporter_id:
        query = query.where(Grievance.reporter_id == reporter_id)
        count_query = count_query.where(Grievance.reporter_id == reporter_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Grievance.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    grievances = result.scalars().unique().all()

    return PaginatedGrievances(
        items=[_to_list_item(g) for g in grievances],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "",
    response_model=GrievanceDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create grievance",
    description="Create a new grievance. Location must be within Delhi ward boundaries. **Access:** any authenticated user (Bearer required).",
    response_description="Created grievance with full detail.",
)
async def create_grievance(
    body: GrievanceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Reject if location is outside Delhi ward boundaries (gpkg)
    ward_info = get_ward_from_location(float(body.lat), float(body.lng))
    if not ward_info:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Location is outside Delhi ward boundaries or could not be verified. Please submit from a valid location within Delhi.",
        )

    # Validate category when provided: require department_id first; category must exist and belong to that department
    if body.category_id is not None:
        if body.department_id is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="When providing category_id, department_id is required. Choose department first, then category from GET /api/v1/departments/{dept_id}/categories",
            )
        cat = await db.execute(select(GrievanceCategory).where(GrievanceCategory.id == body.category_id))
        cat_row = cat.scalar_one_or_none()
        if not cat_row:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"category_id {body.category_id} does not exist. Use a valid category from GET /api/v1/departments/{{dept_id}}/categories",
            )
        if cat_row.dept_id != body.department_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="category_id must belong to the selected department_id. Choose a category from that department.",
            )
    ward_id = body.ward_id
    if ward_id is not None:
        ward_row = await db.execute(select(Ward).where(Ward.id == ward_id))
        if not ward_row.scalar_one_or_none():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"ward_id {ward_id} does not exist. Omit or use a valid ward from GET /api/v1/wards",
            )
    else:
        # Resolve ward from coordinates (DB polygon lookup) so grievance is always ward-scoped
        ward_from_coords = await lookup_ward_by_coords(db, float(body.lat), float(body.lng))
        if ward_from_coords is not None:
            ward_id = ward_from_coords.id
        elif ward_info:
            # Fallback: Use Ward_No from GeoPackage to find the Ward record in the database
            ward_no = ward_info.get("Ward_No")
            if ward_no is not None:
                # ward_no in GeoPackage might be string or int; Ward.number is Integer
                try:
                    ward_num = int(ward_no)
                    ward_fallback = await db.execute(select(Ward).where(Ward.number == ward_num))
                    wf = ward_fallback.scalar_one_or_none()
                    if wf:
                        ward_id = wf.id
                except (ValueError, TypeError):
                    pass

    grievance = Grievance(
        title=body.title,
        description=body.description,
        lat=body.lat,
        lng=body.lng,
        address=body.address,
        priority=body.priority,
        category_id=body.category_id,
        ward_id=ward_id,
        reporter_id=user.id,
        is_sensitive=body.is_sensitive,
    )
    db.add(grievance)
    await db.flush()

    for url in body.media_urls:
        m_type = "audio" if "/audio/" in url else "image"
        db.add(GrievanceMedia(grievance_id=grievance.id, media_url=url, type=m_type))

    db.add(AuditLog(
        grievance_id=grievance.id,
        title="Complaint Registered",
        description=f"Ticket created by {user.name}.",
        icon_name=_audit_icon_for_event(title="Complaint Registered"),
        actor_id=user.id,
    ))

    await db.commit()

    fresh = await db.execute(
        select(Grievance).options(*_GRIEVANCE_DETAIL_OPTIONS).where(Grievance.id == grievance.id)
    )
    return _to_detail(fresh.scalar_one())


@router.get(
    "/{grievance_id}",
    response_model=GrievanceDetail,
    summary="Get grievance by ID",
    description="Return full grievance detail including comments, events, media, assignments. **Access:** public (no auth).",
    response_description="Grievance detail.",
)
async def get_grievance(grievance_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Grievance).options(*_GRIEVANCE_DETAIL_OPTIONS).where(Grievance.id == grievance_id)
    )
    g = result.scalar_one_or_none()
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grievance not found")
    return _to_detail(g)


@router.patch(
    "/{grievance_id}",
    response_model=GrievanceDetail,
    summary="Update grievance",
    description="Update status, priority, or add resolution image. Only **fieldAssistant** or **admin** can update (fieldManager cannot). When status is set to resolved, provide resolution_image_url and optional note. **Access:** fieldAssistant or admin (Bearer required).",
    response_description="Updated grievance detail.",
)
async def update_grievance(
    grievance_id: uuid.UUID,
    body: GrievanceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_can_update_grievance),
):
    result = await db.execute(
        select(Grievance).options(*_GRIEVANCE_DETAIL_OPTIONS).where(Grievance.id == grievance_id)
    )
    g = result.scalar_one_or_none()
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grievance not found")

    if body.status:
        g.status = body.status
    if body.priority:
        g.priority = body.priority
    if body.resolution_image_url:
        db.add(GrievanceMedia(
            grievance_id=g.id, media_url=body.resolution_image_url,
            is_resolution_proof=True,
        ))

    note_text = body.note or f"Status updated to {body.status or g.status}"
    db.add(AuditLog(
        grievance_id=g.id,
        title=body.status or "Updated",
        description=note_text,
        icon_name=_audit_icon_for_event(title=body.status or "Updated", status=body.status),
        actor_id=user.id,
    ))
    g.updated_at = datetime.now(timezone.utc)

    if body.status == "resolved":
        for assignment in g.assignments:
            if assignment.status != "completed":
                assignment.status = "completed"
                assignment.completed_at = datetime.now(timezone.utc)
                if assignment.assigned_to and assignment.assigned_to.worker_profile:
                    wp = assignment.assigned_to.worker_profile
                    wp.tasks_completed = (wp.tasks_completed or 0) + 1
                    wp.tasks_active = max((wp.tasks_active or 1) - 1, 0)

    await db.commit()

    fresh = await db.execute(
        select(Grievance).options(*_GRIEVANCE_DETAIL_OPTIONS).where(Grievance.id == g.id)
    )
    return _to_detail(fresh.scalar_one())


@router.post(
    "/{grievance_id}/assign",
    response_model=GrievanceDetail,
    summary="Assign field assistant to grievance",
    description="Assign a field assistant to the grievance. User must have role fieldAssistant. **Access:** fieldManager or admin only (Bearer required).",
    response_description="Grievance with new assignment.",
)
async def assign_worker(
    grievance_id: uuid.UUID,
    body: AssignWorkerRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    role = getattr(user.role, "value", user.role)
    if role not in ("fieldManager", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Field Manager or Admin can assign field assistants")
    result = await db.execute(
        select(Grievance).options(*_GRIEVANCE_DETAIL_OPTIONS).where(Grievance.id == grievance_id)
    )
    g = result.scalar_one_or_none()
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grievance not found")

    worker_result = await db.execute(
        select(User).options(selectinload(User.worker_profile))
        .where(User.id == body.worker_id, User.role == "fieldAssistant")
    )
    worker = worker_result.scalar_one_or_none()
    if not worker:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Field assistant not found or not a field assistant")

    assignment = Assignment(
        grievance_id=g.id,
        assigned_to_id=worker.id,
        assigned_by_id=user.id,
    )
    db.add(assignment)

    g.status = "assigned"
    g.updated_at = datetime.now(timezone.utc)

    if worker.worker_profile:
        worker.worker_profile.tasks_active = (worker.worker_profile.tasks_active or 0) + 1

    db.add(AuditLog(
        grievance_id=g.id,
        title="Assigned to Field Assistant",
        description=f"Ticket assigned to {worker.name}.",
        icon_name=_audit_icon_for_event(title="Assigned to Field Assistant"),
        actor_id=user.id,
    ))

    await db.commit()

    fresh = await db.execute(
        select(Grievance).options(*_GRIEVANCE_DETAIL_OPTIONS).where(Grievance.id == g.id)
    )
    return _to_detail(fresh.scalar_one())


@router.post(
    "/{grievance_id}/vote",
    status_code=status.HTTP_200_OK,
    summary="Vote on grievance",
    description="Upvote (1), downvote (-1), or remove vote (0). **Access:** any authenticated user (Bearer required).",
    response_description="Updated upvotes and downvotes counts.",
)
async def vote_grievance(
    grievance_id: uuid.UUID,
    body: VoteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Grievance).where(Grievance.id == grievance_id)
    )
    g = result.scalar_one_or_none()
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grievance not found")

    existing = await db.execute(
        select(GrievanceVote).where(
            GrievanceVote.grievance_id == grievance_id,
            GrievanceVote.user_id == user.id,
        )
    )
    vote = existing.scalar_one_or_none()

    if vote:
        old_type = vote.vote_type
        if old_type == body.vote_type:
            await db.delete(vote)
            if body.vote_type == 1:
                g.upvotes_count = max(g.upvotes_count - 1, 0)
            else:
                g.downvotes_count = max(g.downvotes_count - 1, 0)
        else:
            vote.vote_type = body.vote_type
            if body.vote_type == 1:
                g.upvotes_count += 1
                g.downvotes_count = max(g.downvotes_count - 1, 0)
            else:
                g.downvotes_count += 1
                g.upvotes_count = max(g.upvotes_count - 1, 0)
    else:
        db.add(GrievanceVote(
            grievance_id=grievance_id, user_id=user.id, vote_type=body.vote_type,
        ))
        if body.vote_type == 1:
            g.upvotes_count += 1
        else:
            g.downvotes_count += 1

    await db.commit()
    return {"upvotes": g.upvotes_count, "downvotes": g.downvotes_count}


@router.get(
    "/{grievance_id}/comments",
    response_model=list[CommentOut],
    summary="List comments",
    description="List all comments on a grievance. **Access:** public (no auth).",
    response_description="List of comments.",
)
async def list_comments(grievance_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GrievanceComment)
        .options(selectinload(GrievanceComment.user))
        .where(GrievanceComment.grievance_id == grievance_id)
        .order_by(GrievanceComment.created_at)
    )
    comments = result.scalars().all()
    return [
        CommentOut(
            id=c.id, user_id=c.user_id,
            user_name=c.user.name if c.user else None,
            text=c.text, created_at=c.created_at,
        )
        for c in comments
    ]


@router.post(
    "/{grievance_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add comment",
    description="Add a comment to a grievance. **Access:** any authenticated user (Bearer required).",
    response_description="Created comment.",
)
async def add_comment(
    grievance_id: uuid.UUID,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    exists = await db.execute(select(Grievance.id).where(Grievance.id == grievance_id))
    if not exists.scalar_one_or_none():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grievance not found")

    comment = GrievanceComment(
        grievance_id=grievance_id,
        user_id=user.id,
        text=body.text,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    comment_out = CommentOut(
        id=comment.id,
        user_id=comment.user_id,
        user_name=user.name,
        text=comment.text,
        created_at=comment.created_at,
    )

    import asyncio
    asyncio.ensure_future(broadcast_comment(
        str(grievance_id),
        {
            "id": str(comment.id),
            "user_id": str(comment.user_id),
            "user_name": user.name,
            "text": comment.text,
            "created_at": comment.created_at.isoformat(),
        },
    ))

    return comment_out
