import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Text, Boolean, DateTime, Date,
    ForeignKey, Numeric, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID, JSONB, ENUM
from sqlalchemy.orm import relationship

from app.db.database import Base


# ---------------------------------------------------------------------------
# PostgreSQL enum types (created by the SQL migration, NOT by SQLAlchemy)
# ---------------------------------------------------------------------------
user_role_enum = ENUM(
    "citizen", "fieldManager", "fieldAssistant", "admin",
    name="user_role", create_type=False,
)
worker_status_enum = ENUM(
    "onDuty", "offDuty",
    name="worker_status", create_type=False,
)
complaint_status_enum = ENUM(
    "pending", "assigned", "inprogress", "resolved", "escalated",
    name="complaint_status", create_type=False,
)
complaint_priority_enum = ENUM(
    "low", "medium", "high",
    name="complaint_priority", create_type=False,
)
media_type_enum = ENUM(
    "image", "video", "audio",
    name="media_type", create_type=False,
)
assignment_status_enum = ENUM(
    "pending", "accepted", "in_progress", "completed",
    name="assignment_status", create_type=False,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# =========================================================================
# 1. Administrative Structure
# =========================================================================

class Zone(Base):
    __tablename__ = "zones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False)

    wards = relationship("Ward", back_populates="zone")


class PoliticalParty(Base):
    """Political party for ward representatives. Used for party-level analytics."""
    __tablename__ = "political_parties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    short_code = Column(String(50), nullable=True)
    color = Column(String(10), nullable=True)

    wards = relationship("Ward", back_populates="party")


class Ward(Base):
    __tablename__ = "wards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"))
    name = Column(String(255), nullable=False)
    number = Column(Integer, nullable=False)
    polygon_geojson = Column(JSONB)
    representative_name = Column(String(255), nullable=True)
    representative_phone = Column(ARRAY(String), nullable=True)  # list of phone numbers
    party_id = Column(UUID(as_uuid=True), ForeignKey("political_parties.id", ondelete="SET NULL"), nullable=True)
    representative_party = Column(String(255), nullable=True)  # deprecated: use party_id; kept for migration fallback
    representative_email = Column(String(255), nullable=True)

    zone = relationship("Zone", back_populates="wards")
    party = relationship("PoliticalParty", back_populates="wards")


class Department(Base):
    __tablename__ = "departments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    short_code = Column(String(20), nullable=False)
    primary_color = Column(String(10), nullable=False)
    icon = Column(String(100), nullable=False)
    manager_title = Column(String(100), nullable=False)
    assistant_title = Column(String(100), nullable=False)
    jurisdiction_label = Column(String(50), nullable=False)
    sdg = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    categories = relationship("GrievanceCategory", back_populates="department")


# =========================================================================
# 2. Personnel & Identity
# =========================================================================

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(20), unique=True, nullable=False)
    address = Column(Text, nullable=True)
    role = Column(user_role_enum, nullable=False)
    ward = Column(String(255), nullable=True)
    ward_id = Column(UUID(as_uuid=True), ForeignKey("wards.id", ondelete="SET NULL"), nullable=True)
    zone = Column(String(255), nullable=True)
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    last_updated_cis = Column(DateTime(timezone=True), nullable=True)
    cis_score = Column(Numeric(6, 2), nullable=True)

    worker_profile = relationship(
        "WorkerProfile",
        back_populates="user",
        uselist=False,
        foreign_keys="[WorkerProfile.user_id]",
        cascade="all, delete-orphan",
    )
    refresh_tokens = relationship("RefreshToken", back_populates="user")
    cis_snapshots = relationship(
        "CivicImpactScoreSnapshot",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class CisSchedulerState(Base):
    """Singleton row (id=1): anchors rolling CIS periods and next automatic run (IST wall-clock +7d)."""

    __tablename__ = "cis_scheduler_state"

    id = Column(Integer, primary_key=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)


class CivicImpactScoreSnapshot(Base):
    """
    Stored Civic Impact Score (CIS) for a citizen per update cycle.
    week_start / week_end are inclusive calendar dates in Indian Standard Time (IST) for the snapshot period.
    """

    __tablename__ = "civic_impact_score_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    week_start = Column(Date, nullable=False)
    week_end = Column(Date, nullable=False)
    total_score = Column(Numeric(6, 2), nullable=False)
    breakdown = Column(JSONB, nullable=False)
    raw_metrics = Column(JSONB, nullable=False)
    computed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    user = relationship("User", back_populates="cis_snapshots")

    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_cis_user_week"),
        Index("ix_cis_user_week_start_desc", "user_id", "week_start"),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    token = Column(String(512), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    user = relationship("User", back_populates="refresh_tokens")


class WorkerProfile(Base):
    __tablename__ = "worker_profiles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"))
    designation_title = Column(String(255), nullable=False)
    zone_id = Column(UUID(as_uuid=True), ForeignKey("zones.id", ondelete="SET NULL"))
    ward_id = Column(UUID(as_uuid=True), ForeignKey("wards.id", ondelete="SET NULL"))
    supervisor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    rating = Column(Numeric(3, 2), default=0.00)
    ratings_count = Column(Integer, default=0)
    tasks_completed = Column(Integer, default=0)
    tasks_active = Column(Integer, default=0)
    current_status = Column(worker_status_enum, default="offDuty")
    last_active_lat = Column(Numeric(9, 6))
    last_active_lng = Column(Numeric(9, 6))

    user = relationship("User", back_populates="worker_profile", foreign_keys=[user_id])
    department = relationship("Department")
    zone = relationship("Zone")
    ward = relationship("Ward")
    supervisor = relationship("User", foreign_keys=[supervisor_id])

    @property
    def ward_display(self) -> str | None:
        """Ward name for API (staff assigned ward)."""
        if self.ward is None:
            return None
        return self.ward.name


# =========================================================================
# 3. Grievance Ecosystem
# =========================================================================

class GrievanceCategory(Base):
    __tablename__ = "grievance_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dept_id = Column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"))
    name = Column(String(255), nullable=False)

    department = relationship("Department", back_populates="categories")


class Grievance(Base):
    __tablename__ = "grievances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=True)
    description = Column(Text)
    lat = Column(Numeric(9, 6), nullable=False)
    lng = Column(Numeric(9, 6), nullable=False)
    address = Column(String(500))
    status = Column(complaint_status_enum, default="pending")
    priority = Column(complaint_priority_enum, default="medium")
    category_id = Column(UUID(as_uuid=True), ForeignKey("grievance_categories.id", ondelete="SET NULL"))
    ward_id = Column(UUID(as_uuid=True), ForeignKey("wards.id", ondelete="SET NULL"))
    reporter_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    upvotes_count = Column(Integer, default=0)
    downvotes_count = Column(Integer, default=0)
    is_sensitive = Column(Boolean, default=False)
    is_ai_spam = Column(Boolean, default=False)
    ai_suggested_worker_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ai_suggestion_reason = Column(Text, nullable=True)
    citizen_rating = Column(Integer, nullable=True)
    reopen_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    category = relationship("GrievanceCategory")
    ward = relationship("Ward")
    reporter = relationship("User", foreign_keys=[reporter_id])
    ai_suggested_worker = relationship("User", foreign_keys=[ai_suggested_worker_id])
    media = relationship("GrievanceMedia", back_populates="grievance", order_by="GrievanceMedia.created_at")
    votes = relationship("GrievanceVote", back_populates="grievance")
    comments = relationship("GrievanceComment", back_populates="grievance", order_by="GrievanceComment.created_at")
    assignments = relationship("Assignment", back_populates="grievance", order_by="Assignment.assigned_at.desc()")
    audit_logs = relationship("AuditLog", back_populates="grievance", order_by="AuditLog.created_at")
    conversation = relationship("Conversation", back_populates="grievance", uselist=False, cascade="all, delete-orphan")


class GrievanceMedia(Base):
    __tablename__ = "grievance_media"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"))
    media_url = Column(Text, nullable=False)
    type = Column(media_type_enum, default="image")
    is_resolution_proof = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    grievance = relationship("Grievance", back_populates="media")


# =========================================================================
# 4. Social Collaboration
# =========================================================================

class GrievanceVote(Base):
    __tablename__ = "grievance_votes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    vote_type = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("grievance_id", "user_id", name="uq_grievance_user_vote"),
    )

    grievance = relationship("Grievance", back_populates="votes")
    user = relationship("User")


class GrievanceResolutionRating(Base):
    """One row per citizen rating event. Handles reopen: each resolution gets its own rating."""
    __tablename__ = "grievance_resolution_ratings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=False)
    worker_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    grievance = relationship("Grievance")
    worker = relationship("User")


class GrievanceComment(Base):
    __tablename__ = "grievance_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    grievance = relationship("Grievance", back_populates="comments")
    user = relationship("User")


# =========================================================================
# 5. Operations & Workflows
# =========================================================================

class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"))
    assigned_to_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    assigned_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    status = Column(assignment_status_enum, default="pending")
    assigned_at = Column(DateTime(timezone=True), default=_utcnow)
    completed_at = Column(DateTime(timezone=True))

    grievance = relationship("Grievance", back_populates="assignments")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"))
    title = Column(String(255), nullable=False)
    description = Column(Text)
    icon_name = Column(String(100))
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    grievance = relationship("Grievance", back_populates="audit_logs")
    actor = relationship("User")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    date = Column(Date, nullable=False)
    clock_in_time = Column(DateTime(timezone=True), nullable=False)
    clock_in_lat = Column(Numeric(9, 6), nullable=False)
    clock_in_lng = Column(Numeric(9, 6), nullable=False)
    clock_out_time = Column(DateTime(timezone=True))
    clock_out_lat = Column(Numeric(9, 6))
    clock_out_lng = Column(Numeric(9, 6))
    total_duration_seconds = Column(Integer)

    user = relationship("User")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=True)  # Optional name for group chats
    type = Column(String(50), default="dm")    # "dm", "department", or "task"
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    grievance_id = Column(UUID(as_uuid=True), ForeignKey("grievances.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("grievance_id", "type", name="uq_grievance_conversation_type"),
    )

    participants = relationship("ConversationParticipant", back_populates="conversation", cascade="all, delete-orphan")
    messages = relationship("InternalMessage", back_populates="conversation", order_by="InternalMessage.created_at")
    grievance = relationship("Grievance", back_populates="conversation")


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    unread_count = Column(Integer, default=0)
    joined_at = Column(DateTime(timezone=True), default=_utcnow)

    conversation = relationship("Conversation", back_populates="participants")
    user = relationship("User")


class InternalMessage(Base):
    __tablename__ = "internal_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True)
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True) # Keep for migration/compatibility
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
