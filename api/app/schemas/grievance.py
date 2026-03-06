from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GrievanceStatus = Literal["pending", "assigned", "inprogress", "resolved"]


# ---------------------------------------------------------------------------
# Nested read schemas
# ---------------------------------------------------------------------------

class CommentOut(BaseModel):
    """A comment on a grievance."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Comment UUID.")
    user_id: uuid.UUID = Field(..., description="Author user UUID.")
    user_name: str | None = Field(None, description="Author display name.")
    text: str = Field(..., description="Comment text.")
    created_at: datetime = Field(..., description="When the comment was created.")


class AuditLogOut(BaseModel):
    """An event in the grievance timeline (status change, assignment, etc.)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Event UUID.")
    title: str = Field(..., description="Event title.")
    description: str | None = Field(None, description="Event description.")
    icon_name: str | None = Field(None, description="Icon name for UI.")
    created_at: datetime = Field(..., description="When the event occurred.")


class MediaOut(BaseModel):
    """Media attached to a grievance (image or video); may be resolution proof."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Media UUID.")
    media_url: str = Field(..., description="URL of the media file.")
    type: str = Field(..., description="One of: image, video, audio.")
    is_resolution_proof: bool = Field(..., description="True if this is the resolution proof image.")
    created_at: datetime = Field(..., description="When the media was added.")


class AssignmentOut(BaseModel):
    """Assignment of a field assistant to a grievance."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Assignment UUID.")
    assigned_to_id: uuid.UUID = Field(..., description="Field assistant (user) UUID.")
    assigned_to_name: str | None = Field(None, description="Field assistant display name.")
    assigned_to_phone: str | None = Field(None, description="Field assistant phone.")
    assigned_by_id: uuid.UUID | None = Field(None, description="User who assigned (manager/admin) UUID.")
    status: str = Field(..., description="pending, accepted, in_progress, or completed.")
    assigned_at: datetime = Field(..., description="When the assignment was created.")
    completed_at: datetime | None = Field(None, description="When the assignment was completed (if resolved).")


# ---------------------------------------------------------------------------
# Grievance read schemas
# ---------------------------------------------------------------------------

class GrievanceListItem(BaseModel):
    """Grievance summary in list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Grievance UUID.")
    title: str | None = Field(None, description="Grievance title.")
    description: str | None = Field(None, description="Detailed description.")
    lat: Decimal = Field(..., description="Latitude of the issue location.")
    lng: Decimal = Field(..., description="Longitude of the issue location.")
    address: str | None = Field(None, description="Address or place name.")
    status: str = Field(..., description="pending, assigned, inprogress, or resolved.")
    priority: str = Field(..., description="low, medium, or high.")
    category_name: str | None = Field(None, description="Grievance category name.")
    category_dept_id: uuid.UUID | None = Field(None, description="Department UUID of the category.")
    ward_name: str | None = Field(None, description="Ward name.")
    ward_number: int | None = Field(None, description="Ward number.")
    reporter_name: str | None = Field(None, description="Name of the citizen who reported.")
    upvotes_count: int = Field(..., description="Number of upvotes.")
    downvotes_count: int = Field(..., description="Number of downvotes.")
    created_at: datetime = Field(..., description="When the grievance was created.")
    image_url: str | None = Field(None, description="URL of the first non-resolution image.")
    audio_url: str | None = Field(None, description="URL of the first audio recording.")
    is_sensitive: bool = Field(False, description="True if the image contains disturbing content.")
    assigned_to_name: str | None = Field(None, description="Name of the currently assigned field assistant.")
    assigned_to_id: uuid.UUID | None = Field(None, description="UUID of the currently assigned field assistant.")


class GrievanceDetail(GrievanceListItem):
    """Full grievance detail with comments, events, media, and assignments."""

    reporter_id: uuid.UUID | None = Field(None, description="Reporter user UUID.")
    worker_contact: str | None = Field(None, description="Phone of the assigned field assistant.")
    resolution_image_url: str | None = Field(None, description="URL of resolution proof image (deprecated; use resolution_media_url).")
    resolution_media_url: str | None = Field(None, description="URL of resolution proof media when status is resolved.")
    comments: list[CommentOut] = Field(default_factory=list, description="Comments on the grievance.")
    events: list[AuditLogOut] = Field(default_factory=list, description="Timeline events (audit log).")
    media: list[MediaOut] = Field(default_factory=list, description="All attached media.")
    assignments: list[AssignmentOut] = Field(default_factory=list, description="Assignment history.")


# ---------------------------------------------------------------------------
# Write schemas
# ---------------------------------------------------------------------------

class GrievanceCreate(BaseModel):
    """Request body for creating a grievance. Access: any authenticated user. Send department_id first; category_id must belong to that department."""

    title: str | None = Field(None, max_length=255, description="Short title of the grievance.")
    description: str | None = Field(None, description="Optional detailed description.")
    lat: Decimal = Field(..., description="Latitude of the issue location.")
    lng: Decimal = Field(..., description="Longitude of the issue location.")
    address: str | None = Field(None, description="Optional address or place name.")
    priority: str = Field(default="medium", description="low, medium, or high.")
    department_id: uuid.UUID | None = Field(None, description="Department UUID (choose first; categories are filtered by this).")
    category_id: uuid.UUID | None = Field(None, description="Grievance category UUID (must belong to department_id).")
    ward_id: uuid.UUID | None = Field(None, description="Ward UUID (optional).")
    media_urls: list[str] = Field(default_factory=list, description="URLs of images/videos to attach.")
    is_sensitive: bool = Field(False, description="Flag as sensitive content.")


class GrievanceUpdate(BaseModel):
    """Request body for updating a grievance. Access: fieldAssistant or admin only (not fieldManager)."""

    status: GrievanceStatus | None = Field(None, description="New status: pending, assigned, inprogress, or resolved.")
    priority: str | None = Field(None, description="New priority: low, medium, or high.")
    resolution_image_url: str | None = Field(None, description="URL of resolution proof image (when marking resolved).")
    note: str | None = Field(None, description="Optional note for the status update.")


class AssignWorkerRequest(BaseModel):
    """Request body for assigning a field assistant to a grievance. Access: fieldManager or admin."""

    worker_id: uuid.UUID = Field(..., description="UUID of the field assistant to assign.")


class VoteRequest(BaseModel):
    """Request body for voting on a grievance. Access: any authenticated user."""

    vote_type: int = Field(..., ge=-1, le=1, description="1 = upvote, -1 = downvote, 0 = remove vote.")


class CommentCreate(BaseModel):
    """Request body for adding a comment. Access: any authenticated user."""

    text: str = Field(..., min_length=1, description="Comment text.")


# ---------------------------------------------------------------------------
# Pagination wrapper
# ---------------------------------------------------------------------------

class PaginatedGrievances(BaseModel):
    """Paginated list of grievances."""

    items: list[GrievanceListItem] = Field(..., description="Page of grievance items.")
    total: int = Field(..., description="Total number of grievances matching the filter.")
    skip: int = Field(..., description="Number of items skipped (offset).")
    limit: int = Field(..., description="Page size (limit).")
