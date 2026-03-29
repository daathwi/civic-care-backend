from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy import String, func, select, case, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user, require_can_update_grievance, require_manager
from app.db.database import get_db
from app.services.delhi_ward_lookup import get_ward_from_location
from app.services.ward_lookup import lookup_ward_by_coords
from app.services.worker_rating_service import recalculate_worker_rating
from app.models.models import (
    Assignment, AuditLog, Grievance, GrievanceCategory,
    GrievanceComment, GrievanceMedia, GrievanceResolutionRating, GrievanceVote,
    User, Ward, WorkerProfile, Conversation
)
from app.services.eps_service import get_ward_maxima, calculate_eps
from app.services.ollama_service import is_spam, recommend_worker_task
from app.schemas.grievance import (
    AssignWorkerRequest, AssignmentOut, AuditLogOut,
    CommentCreate, CommentOut, GrievanceCreate, GrievanceDetail,
    GrievanceListItem, GrievanceUpdate, MediaOut,
    PaginatedGrievances, RateGrievanceRequest, VoteRequest,
)
from app.api.v1.endpoints.chat import broadcast_comment

router = APIRouter(prefix="/grievances", tags=["grievances"])
MAX_REOPEN_BEFORE_ESCALATION = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Icon names for audit log events; must match Flutter iconFromApi() in grievance_mappers.dart.
def _audit_icon_for_event(title: str | None = None, status: str | None = None) -> str:
    """Return the icon_name to store for an audit log entry. Used whenever any role writes an AuditLog."""
    t = (str(title) if title is not None else "").strip().lower()
    # Normalize status to string if it's an enum member
    s_val = str(status.value if hasattr(status, "value") else (status or "")).strip().lower()
    
    if "registered" in t or "created" in t or "complaint" in t:
        return "article_outlined"
    if "assigned" in t or "assignment" in t:
        return "assignment_ind_rounded"
    if s_val == "resolved" or "resolved" in t or "completed" in t:
        return "check_circle_outline_rounded"
    if s_val == "inprogress" or "in progress" in t or "ongoing" in t:
        return "update_rounded"
    if s_val == "pending" or "pending" in t:
        return "schedule_rounded"
    if s_val == "assigned":
        return "assignment_ind_rounded"
    if s_val == "escalated" or "escalated" in t:
        return "report_problem"
    # Default for generic "Updated" or unknown
    return "update_rounded"


def _to_list_item(g: Grievance) -> GrievanceListItem:
    active = next(
        (a for a in (g.assignments or []) if a.status != "completed"),
        None,
    )
    # For resolved grievances, all assignments are completed; use most recent for assigned_to
    assignee = active if active else (g.assignments[0] if g.assignments else None)
    first_image = next(
        (m.media_url for m in (g.media or []) if m.type == "image" and not m.is_resolution_proof),
        None,
    )
    first_audio = next(
        (m.media_url for m in (g.media or []) if m.type == "audio"),
        None,
    )
    # Effective priority: reopens bump severity (reopen_count >= 2 → high; reopen_count == 1 → bump one level)
    stored = (g.priority or "medium").lower()
    rc = g.reopen_count or 0
    if rc >= 2:
        effective = "high"
    elif rc == 1:
        effective = "high" if stored in ("medium", "high") else "medium"
    else:
        effective = stored
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
        department_name=g.category.department.name if g.category and g.category.department else None,
        ward_name=g.ward.name if g.ward else None,
        ward_number=g.ward.number if g.ward else None,
        zone_name=g.ward.zone.name if g.ward and g.ward.zone else None,
        reporter_name=g.reporter.name if g.reporter else None,
        reporter_phone=g.reporter.phone if g.reporter else None,
        upvotes_count=g.upvotes_count,
        downvotes_count=g.downvotes_count,
        created_at=g.created_at,
        image_url=first_image,
        audio_url=first_audio,
        is_sensitive=g.is_sensitive,
        citizen_rating=g.citizen_rating,
        reopen_count=g.reopen_count,
        effective_priority=effective,
        assigned_to_name=assignee.assigned_to.name if assignee and assignee.assigned_to else None,
        assigned_to_id=assignee.assigned_to_id if assignee else None,
        assigned_to_phone=assignee.assigned_to.phone if assignee and assignee.assigned_to else None,
        ai_suggested_worker_id=g.ai_suggested_worker_id,
        ai_suggested_worker_name=g.ai_suggested_worker.name if g.ai_suggested_worker else None,
        ai_suggestion_reason=g.ai_suggestion_reason,
    )


def _to_detail(g: Grievance) -> GrievanceDetail:
    active = next(
        (a for a in (g.assignments or []) if a.status != "completed"),
        None,
    )
    assignee = active if active else (g.assignments[0] if g.assignments else None)
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
            actor_id=e.actor_id,
            actor_name=e.actor.name if e.actor else None,
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
            assigned_by_name=a.assigned_by.name if a.assigned_by else None,
            assigned_by_phone=a.assigned_by.phone if a.assigned_by else None,
            status=a.status,
            assigned_at=a.assigned_at,
            completed_at=a.completed_at,
        )
        for a in (g.assignments or [])
    ]

    stored = (g.priority or "medium").lower()
    rc = g.reopen_count or 0
    if rc >= 2:
        effective = "high"
    elif rc == 1:
        effective = "high" if stored in ("medium", "high") else "medium"
    else:
        effective = stored

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
        department_name=g.category.department.name if g.category and g.category.department else None,
        ward_name=g.ward.name if g.ward else None,
        ward_number=g.ward.number if g.ward else None,
        reporter_id=g.reporter_id,
        reporter_name=g.reporter.name if g.reporter else None,
        reporter_phone=g.reporter.phone if g.reporter else None,
        upvotes_count=g.upvotes_count,
        downvotes_count=g.downvotes_count,
        created_at=g.created_at,
        image_url=first_image,
        is_sensitive=g.is_sensitive,
        citizen_rating=g.citizen_rating,
        reopen_count=g.reopen_count,
        effective_priority=effective,
        assigned_to_name=assignee.assigned_to.name if assignee and assignee.assigned_to else None,
        assigned_to_id=assignee.assigned_to_id if assignee else None,
        worker_contact=assignee.assigned_to.phone if assignee and assignee.assigned_to else None,
        assigned_by_name=assignee.assigned_by.name if assignee and assignee.assigned_by else None,
        assigned_by_phone=assignee.assigned_by.phone if assignee and assignee.assigned_by else None,
        resolution_image_url=resolution_img,
        resolution_media_url=resolution_img,
        ai_suggested_worker_name=g.ai_suggested_worker.name if g.ai_suggested_worker else None,
        ai_suggestion_reason=g.ai_suggestion_reason,
        comments=comments_out,
        events=events_out,
        media=media_out,
        assignments=assignments_out,
    )


_GRIEVANCE_LOAD_OPTIONS = [
    selectinload(Grievance.category).selectinload(GrievanceCategory.department),
    selectinload(Grievance.ward).selectinload(Ward.zone),
    selectinload(Grievance.reporter),
    selectinload(Grievance.ai_suggested_worker),
    selectinload(Grievance.media),
    selectinload(Grievance.assignments).selectinload(Assignment.assigned_to).selectinload(User.worker_profile),
    selectinload(Grievance.assignments).selectinload(Assignment.assigned_by),
]

_GRIEVANCE_DETAIL_OPTIONS = [
    *_GRIEVANCE_LOAD_OPTIONS,
    selectinload(Grievance.comments).selectinload(GrievanceComment.user),
    selectinload(Grievance.audit_logs).selectinload(AuditLog.actor),
    selectinload(Grievance.conversation),
]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=PaginatedGrievances,
    summary="Browse reported issues",
    description="Look through all the issues reported by citizens. You can filter by category, status, or location.",
    operation_id="browseGrievances",
    response_description="Paginated list of grievance items and total count.",
)
async def list_grievances(
    db: AsyncSession = Depends(get_db),
    zone_id: uuid.UUID | None = Query(None, description="Filter by zone UUID. Returns grievances in wards of this zone. [system centric]"),
    ward_id: uuid.UUID | None = Query(None, description="Filter by ward UUID. [system centric]"),
    ward_name: str | None = Query(None, description="Filter by ward name (partial match). [human centric]"),
    status: str | None = Query(None, description="Filter by status: pending, assigned, inprogress, resolved, escalated. [human centric]"),
    priority: str | None = Query(None, description="Filter by priority: low, medium, high. [human centric]"),
    use_effective_priority: bool = Query(False, description="When True, priority filter uses effective priority (stored + reopen_count)."),
    category_dept: uuid.UUID | None = Query(None, description="Filter by category's department UUID. [system centric]"),
    reporter_id: uuid.UUID | None = Query(None, description="Filter by reporter user UUID. [system centric]"),
    worker_id: uuid.UUID | None = Query(None, description="Filter by assigned worker UUID. [system centric]"),
    skip: int = Query(0, ge=0, description="Number of items to skip (offset). [system centric]"),
    limit: int = Query(10, ge=1, le=100, description="Page size (default 10). [system centric]"),
):
    query = select(Grievance).options(*_GRIEVANCE_LOAD_OPTIONS).where(Grievance.is_ai_spam.is_not(True))
    count_query = select(func.count(Grievance.id)).where(Grievance.is_ai_spam.is_not(True))

    if zone_id:
        query = query.join(Grievance.ward).where(Ward.zone_id == zone_id)
        count_query = count_query.join(Grievance.ward).where(Ward.zone_id == zone_id)
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
        if use_effective_priority:
            rc = func.coalesce(Grievance.reopen_count, 0)
            pri = func.coalesce(cast(Grievance.priority, String), "medium")
            eff_pri = case(
                (rc >= 2, "high"),
                ((rc == 1) & (pri.in_(["medium", "high"])), "high"),
                ((rc == 1) & (pri == "low"), "medium"),
                else_=pri,
            )
            query = query.where(eff_pri == priority)
            count_query = count_query.where(eff_pri == priority)
        else:
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
    if worker_id:
        query = query.join(Grievance.assignments).where(Assignment.assigned_to_id == worker_id)
        count_query = count_query.join(Grievance.assignments).where(Assignment.assigned_to_id == worker_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(Grievance.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    grievances = result.scalars().unique().all()

    # Populate EPS for escalated items
    escalated_items = [g for g in grievances if g.status == "escalated"]
    eps_map = {}
    if escalated_items:
        ward_ids = list({g.ward_id for g in escalated_items if g.ward_id})
        maxima = await get_ward_maxima(db, ward_ids)
        for g in escalated_items:
            m = maxima.get(g.ward_id, {"max_age": 1.0, "max_netvotes": 1.0})
            eps_data = calculate_eps(g, m["max_age"], m["max_netvotes"])
            eps_map[g.id] = eps_data["total"]

    items = []
    for g in grievances:
        item = _to_list_item(g)
        if g.id in eps_map:
            item.eps_score = eps_map[g.id]
        items.append(item)

    return PaginatedGrievances(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "",
    response_model=GrievanceListItem,
    status_code=status.HTTP_201_CREATED,
    summary="Report a new grievance",
    operation_id="createGrievance",
)
async def create_grievance(
    body: GrievanceCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Reject if location is outside Delhi ward boundaries (gpkg)
    ward_info = await run_in_threadpool(get_ward_from_location, float(body.lat), float(body.lng))
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

    # AI Spam Detection (Phase 1)
    dept_name = "Unknown"
    cat_name = "Unknown"
    
    if body.department_id:
        from app.models.models import Department
        dept_res = await db.execute(select(Department).where(Department.id == body.department_id))
        dept_row = dept_res.scalar_one_or_none()
        if dept_row:
            dept_name = dept_row.name
            
    if body.category_id:
        cat_res = await db.execute(select(GrievanceCategory).where(GrievanceCategory.id == body.category_id))
        cat_row = cat_res.scalar_one_or_none()
        if cat_row:
            cat_name = cat_row.name

    ai_is_spam = await is_spam(
        title=body.title, 
        description=body.description,
        department=dept_name,
        category=cat_name
    )

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
        is_ai_spam=ai_is_spam,
    )
    db.add(grievance)
    await db.flush()

    if not ai_is_spam:
        # AI Worker Recommendation (Phase 2) - now in background
        background_tasks.add_task(recommend_worker_task, grievance.id)

    if ai_is_spam:
        # Penalize user by creating the spam record (which affects CIS) then rejecting the request.
        # Audit log for spam penalty
        db.add(AuditLog(
            grievance_id=grievance.id,
            title="AI Spam Detection",
            description="Grievance flagged as spam by AI. User penalized.",
            icon_name="block_rounded",
            actor_id=user.id,
        ))
        await db.commit()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="AI detection has flagged this submission as spam. Your Civic Impact Score has been penalized.",
        )

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
    summary="View issue details",
    description="See the full history and details of a specific reported issue.",
    operation_id="fetchGrievanceDetails",
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
    summary="Update issue status",
    description="Use this to change the status of an issue, like marking it as resolved by adding a proof photo.",
    operation_id="updateGrievanceProgress",
    response_description="Updated grievance detail.",
)
async def update_grievance(
    grievance_id: uuid.UUID,
    body: GrievanceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_can_update_grievance),
):
    print(f"DEBUG: Updating grievance {grievance_id} with body: {body}")
    result = await db.execute(
        select(Grievance).options(*_GRIEVANCE_DETAIL_OPTIONS).where(Grievance.id == grievance_id)
    )
    g = result.scalar_one_or_none()
    if not g:
        print(f"DEBUG: Grievance {grievance_id} not found")
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grievance not found")

    if body.status:
        print(f"DEBUG: Setting status from {g.status} to {body.status}")
        g.status = body.status
    if body.priority:
        g.priority = body.priority
    if body.resolution_image_url:
        print(f"DEBUG: Adding resolution image: {body.resolution_image_url}")
        db.add(GrievanceMedia(
            grievance_id=g.id, media_url=body.resolution_image_url,
            is_resolution_proof=True,
        ))

    note_text = body.note or f"Status updated to {body.status or g.status}"
    db.add(AuditLog(
        grievance_id=g.id,
        title=str(body.status.value if hasattr(body.status, "value") else (body.status or "Updated")),
        description=note_text,
        icon_name=_audit_icon_for_event(title=body.status or "Updated", status=body.status),
        actor_id=user.id,
    ))
    g.updated_at = datetime.now(timezone.utc)

    if body.status and body.status.value == "resolved":
        g.citizen_rating = None  # Clear previous rating to allow re-rating
        print(f"DEBUG: Resolving grievance, updating assignments...")
        for assignment in g.assignments:
            if assignment.status != "completed":
                print(f"DEBUG: Completing assignment {assignment.id}")
                assignment.status = "completed"
                assignment.completed_at = datetime.now(timezone.utc)
                if assignment.assigned_to and assignment.assigned_to.worker_profile:
                    wp = assignment.assigned_to.worker_profile
                    wp.tasks_completed = (wp.tasks_completed or 0) + 1
                    wp.tasks_active = max((wp.tasks_active or 1) - 1, 0)
        
        # Delete associated conversation when resolved
        if g.conversation:
            print(f"DEBUG: Deleting conversation {g.conversation.id}")
            await db.delete(g.conversation)

    print(f"DEBUG: Committing changes for grievance {grievance_id}")
    await db.commit()

    fresh = await db.execute(
        select(Grievance).options(*_GRIEVANCE_DETAIL_OPTIONS).where(Grievance.id == g.id)
    )
    res_obj = fresh.scalar_one()
    print(f"DEBUG: Update complete. Final status: {res_obj.status}")
    return _to_detail(res_obj)


@router.post(
    "/{grievance_id}/assign",
    response_model=GrievanceDetail,
    summary="Assign someone to help",
    description="Assign a field worker to take care of this specific issue.",
    operation_id="assignWorkerToGrievance",
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

    # ── Close any existing active assignments (reassignment) ──────────────
    previous_worker_name = None
    for old_assignment in (g.assignments or []):
        if old_assignment.status not in ("completed",):
            old_assignment.status = "completed"
            old_assignment.completed_at = datetime.now(timezone.utc)
            if old_assignment.assigned_to:
                previous_worker_name = old_assignment.assigned_to.name
                if old_assignment.assigned_to.worker_profile:
                    wp = old_assignment.assigned_to.worker_profile
                    wp.tasks_active = max((wp.tasks_active or 1) - 1, 0)

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

    # Audit log — differentiate new assignment vs reassignment
    if previous_worker_name:
        db.add(AuditLog(
            grievance_id=g.id,
            title="Reassigned to Field Assistant",
            description=f"Ticket reassigned from {previous_worker_name} to {worker.name}.",
            icon_name=_audit_icon_for_event(title="Assigned to Field Assistant"),
            actor_id=user.id,
        ))
    else:
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
    summary="Support this issue",
    description="Show your support for an issue reported by others to help prioritize it.",
    operation_id="voteOnGrievance",
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
    summary="Read discussion",
    description="See all the comments and updates shared about this issue.",
    operation_id="listGrievanceComments",
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
    summary="Add your comment",
    description="Share an update or ask a question about this issue.",
    operation_id="postGrievanceComment",
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


@router.post(
    "/{grievance_id}/rate",
    response_model=GrievanceDetail,
    summary="Rate the resolution",
    description="Let us know if you are happy with how the issue was resolved.",
    operation_id="rateResolutionQuality",
    response_description="Updated grievance detail.",
)
async def rate_grievance(
    grievance_id: uuid.UUID,
    body: RateGrievanceRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Grievance).options(*_GRIEVANCE_DETAIL_OPTIONS).where(Grievance.id == grievance_id)
    )
    g = result.scalar_one_or_none()
    if not g:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grievance not found")

    if g.reporter_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the original reporter can rate this grievance")

    if g.status != "resolved":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only resolved grievances can be rated")

    g.citizen_rating = body.rating
    g.updated_at = datetime.now(timezone.utc)

    # Store rating per resolution (handles reopen: each worker gets their own rating)
    resolver_id = None
    completed = [a for a in (g.assignments or []) if a.status == "completed"]
    if completed:
        latest = max(completed, key=lambda a: a.assigned_at or datetime.min)
        resolver_id = latest.assigned_to_id
    if resolver_id:
        db.add(GrievanceResolutionRating(
            grievance_id=g.id,
            worker_id=resolver_id,
            rating=body.rating,
        ))

    if body.rating < 3:
        # Low rating: reopen initially; escalate from the 3rd reopen onward.
        g.citizen_rating = body.rating  # Keep the rating for record
        g.reopen_count = (g.reopen_count or 0) + 1
        if (g.reopen_count or 0) >= MAX_REOPEN_BEFORE_ESCALATION:
            g.status = "escalated"
            db.add(AuditLog(
                grievance_id=g.id,
                title="Escalated — Repeated Reopen",
                description=(
                    f"Citizen rated resolution {body.rating}/5. "
                    f"Ticket escalated after {g.reopen_count} low-rating reopens."
                ),
                icon_name=_audit_icon_for_event(title="escalated", status="escalated"),
                actor_id=user.id,
            ))
        else:
            g.status = "pending"
            db.add(AuditLog(
                grievance_id=g.id,
                title="Reopened — Low Rating",
                description=f"Citizen rated resolution {body.rating}/5. Ticket reopened for review.",
                icon_name=_audit_icon_for_event(title="pending", status="pending"),
                actor_id=user.id,
            ))
    else:
        db.add(AuditLog(
            grievance_id=g.id,
            title="Citizen Rated Resolution",
            description=f"Citizen rated the resolution {body.rating}/5.",
            icon_name=_audit_icon_for_event(title="Resolved", status="resolved"),
            actor_id=user.id,
        ))

    await db.commit()

    # Recalculate worker rating from citizen ratings (resolver = most recent completed assignment)
    resolver_id = None
    completed = [a for a in (g.assignments or []) if a.status == "completed"]
    if completed:
        latest = max(completed, key=lambda a: a.assigned_at or datetime.min)
        resolver_id = latest.assigned_to_id
    if resolver_id:
        await recalculate_worker_rating(db, worker_id=resolver_id)
        await db.commit()

    fresh = await db.execute(
        select(Grievance).options(*_GRIEVANCE_DETAIL_OPTIONS).where(Grievance.id == g.id)
    )
    return _to_detail(fresh.scalar_one())
