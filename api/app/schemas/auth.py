from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    """Request body for citizen registration."""

    name: str = Field(..., min_length=1, max_length=255, description="Full name of the citizen. [human centric]")
    email: str | None = Field(None, max_length=255, description="Email address. [human centric]")
    phone: str = Field(..., min_length=10, max_length=20, description="Unique phone number (used for login). [human centric]")
    address: str | None = Field(None, description="Residential address. [human centric]")
    password: str = Field(..., min_length=6, description="Password for login. [human centric]")
    confirm_password: str = Field(..., min_length=6, description="Must match password. [human centric]")
    zone_id: uuid.UUID | None = Field(None, description="Zone UUID from dropdown. [system centric]")
    ward_id: uuid.UUID | None = Field(None, description="Ward UUID from dropdown (filtered by zone). [system centric]")
    ward_number: int | None = Field(None, description="Optional ward number for display. [human centric]")
    lat: float | None = Field(None, description="Latitude; if provided with lng, ward/zone are set from Delhi wards GeoPackage. [human centric]")
    lng: float | None = Field(None, description="Longitude; if provided with lat, ward/zone are set from Delhi wards GeoPackage. [human centric]")

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class LoginRequest(BaseModel):
    """Login: provide exactly one of phone or user_id, plus password. Staff can use user_id (UUID) or phone number."""

    phone: str | None = Field(None, description="Phone number (for citizen login). Omit if using user_id. [human centric]")
    user_id: str | None = Field(None, description="User ID (UUID) or phone number for department staff. Omit if using phone for citizen. [human centric]")
    password: str = Field(..., description="Password. [human centric]")
    department: uuid.UUID | None = Field(None, description="Optional department UUID; if provided, login succeeds only if user belongs to this department. [system centric]")

    @model_validator(mode="after")
    def require_phone_or_user_id(self):
        has_phone = self.phone is not None and str(self.phone).strip() != ""
        has_user_id = self.user_id is not None and str(self.user_id).strip() != ""
        if has_phone == has_user_id:
            raise ValueError("Provide exactly one of 'phone' or 'user_id'")
        return self


class RefreshRequest(BaseModel):
    """Request body for refreshing access token."""

    refresh_token: str = Field(..., description="Valid refresh token from login or previous refresh.")


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    """JWT tokens for authenticated requests."""

    access_token: str = Field(..., description="JWT access token; send in Authorization: Bearer <access_token>.")
    refresh_token: str = Field(..., description="Refresh token; use in POST /auth/refresh to get new tokens.")
    token_type: str = Field(default="bearer", description="Token type (bearer).")


class DepartmentOut(BaseModel):
    """Department as returned in list/detail responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Department UUID.")
    name: str = Field(..., description="Department display name.")
    short_code: str = Field(..., description="Short code (e.g. SW, ENG).")
    primary_color: str = Field(..., description="Hex or theme color for UI.")
    icon: str = Field(..., description="Icon name for UI.")
    manager_title: str = Field(..., description="Title for department manager.")
    assistant_title: str = Field(..., description="Title for field assistants.")
    jurisdiction_label: str = Field(..., description="Jurisdiction label (e.g. Ward, Cluster of wards).")
    sdg: str | None = Field(None, description="Linked SDG identifier/title for this department.")
    description: str | None = Field(None, description="Short department description.")


class DepartmentCreate(BaseModel):
    """Request body for creating a department. Access: fieldManager or admin."""

    name: str = Field(..., description="Department display name.")
    short_code: str = Field(..., description="Unique short code (e.g. SW, ENG).")
    primary_color: str = Field(default="#1976D2", description="Hex color for UI.")
    icon: str = Field(default="assignment", description="Icon name.")
    manager_title: str = Field(default="Manager", description="Manager job title.")
    assistant_title: str = Field(default="Assistant", description="Assistant job title.")
    jurisdiction_label: str = Field(default="Ward", description="Jurisdiction label.")
    sdg: str | None = Field(None, description="Linked SDG identifier/title.")
    description: str | None = Field(None, description="Department description.")


class DepartmentUpdate(BaseModel):
    """Request body for updating a department. Access: fieldManager or admin."""

    name: str | None = Field(None, description="Department display name.")
    short_code: str | None = Field(None, description="Unique short code.")
    primary_color: str | None = Field(None, description="Hex color for UI.")
    icon: str | None = Field(None, description="Icon name.")
    manager_title: str | None = Field(None, description="Manager job title.")
    assistant_title: str | None = Field(None, description="Assistant job title.")
    jurisdiction_label: str | None = Field(None, description="Jurisdiction label.")
    sdg: str | None = Field(None, description="Linked SDG identifier/title.")
    description: str | None = Field(None, description="Department description.")


class WorkerProfileBrief(BaseModel):
    """Field assistant profile summary nested in UserOut.

    Required for Flutter department portal: login and GET /auth/me must return
    worker_profile with department_id, ward_display, and department (name/short_code)
    so the app can set ward, department, and filter workers/grievances correctly.
    """

    model_config = ConfigDict(from_attributes=True)

    department_id: uuid.UUID | None = Field(None, description="Department UUID (required for staff list filters).")
    department: DepartmentOut | None = Field(None, description="Department details when loaded (name, short_code for UI).")
    designation_title: str = Field(..., description="Job designation.")
    ward_id: uuid.UUID | None = Field(None, description="Ward UUID if assigned.")
    ward_display: str | None = Field(None, description="Ward name when assigned (for staff Assigned Ward; used by app for display and filtering).")
    current_status: str | None = Field(None, description="onDuty or offDuty.")
    rating: float | None = Field(None, description="Average citizen rating from resolved grievances.")
    ratings_count: int = Field(0, description="Number of citizen ratings received.")
    tasks_completed: int = Field(0, description="Number of tasks completed.")
    tasks_active: int = Field(0, description="Number of active tasks.")

    @field_validator("tasks_completed", "tasks_active", "ratings_count", mode="before")
    @classmethod
    def coerce_none_to_zero(cls, v: int | None) -> int:
        return 0 if v is None else v


class UserOut(BaseModel):
    """Authenticated user info (login/register/me response)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="User UUID.")
    name: str = Field(..., description="Display name.")
    email: str | None = Field(None, description="Email address.")
    phone: str = Field(..., description="Phone number.")
    address: str | None = Field(None, description="Residential address.")
    role: str = Field(..., description="One of: citizen, fieldManager, fieldAssistant, admin.")
    ward: str | None = Field(None, description="Ward display string (for citizens).")
    ward_id: uuid.UUID | None = Field(None, description="Ward UUID (for citizens).")
    zone: str | None = Field(None, description="Zone display string (for citizens).")
    zone_id: uuid.UUID | None = Field(None, description="Zone UUID (for citizens).")
    created_at: datetime | None = Field(None, description="Account creation time.")
    worker_profile: WorkerProfileBrief | None = Field(None, description="Present for staff; null for citizens.")
    cis_total_score: float | None = Field(
        None,
        description="Latest Civic Impact Score (0–100); mirrored from `users.cis_score` after Update CIS, else snapshot.",
    )
    cis_week_start: date | None = Field(None, description="IST period start date for the CIS snapshot (if any).")
    cis_week_end: date | None = Field(None, description="IST period end date (inclusive) for the CIS snapshot (if any).")
    cis_computed_at: datetime | None = Field(None, description="When the CIS snapshot was computed (UTC in API; display as IST).")
    last_updated_cis: datetime | None = Field(
        None,
        description="When this citizen’s CIS snapshot was last refreshed (same as snapshot run; use IST in UI).",
    )


class AuthResponse(BaseModel):
    """Response for login and register: user info and tokens."""

    user: UserOut = Field(..., description="Authenticated user.")
    tokens: TokenResponse = Field(..., description="Access and refresh tokens.")
