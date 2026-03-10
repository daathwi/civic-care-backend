from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkerCreate(BaseModel):
    """Request body for creating a field assistant (user + worker profile). Access: fieldManager or admin."""

    # User attributes (workers are users)
    name: str = Field(..., description="Full name.")
    email: str | None = Field(None, description="Email address.")
    phone: str = Field(..., description="Unique phone number (used for login).")
    address: str | None = Field(None, description="Address or location.")
    password: str = Field(..., description="Initial password for the worker.")
    role: str = Field(default="fieldAssistant", description="fieldAssistant or fieldManager.")
    # Worker profile attributes
    designation_title: str = Field(..., description="Job designation (e.g. Field Worker, Junior Engineer).")
    department_id: uuid.UUID | None = Field(None, description="Department UUID.")
    zone_id: uuid.UUID | None = Field(None, description="Zone UUID.")
    ward_id: uuid.UUID | None = Field(None, description="Ward UUID.")


class WorkerUpdate(BaseModel):
    """Request body for updating a field assistant. Access: fieldManager or admin."""

    name: str | None = Field(None, description="Full name.")
    email: str | None = Field(None, description="Email address.")
    phone: str | None = Field(None, description="Unique phone number.")
    address: str | None = Field(None, description="Address or location.")
    password: str | None = Field(None, description="New password (optional).")
    role: str | None = Field(None, description="fieldAssistant or fieldManager.")
    designation_title: str | None = Field(None, description="Job designation.")
    department_id: uuid.UUID | None = Field(None, description="Department UUID.")
    zone_id: uuid.UUID | None = Field(None, description="Zone UUID.")
    ward_id: uuid.UUID | None = Field(None, description="Ward UUID.")


class WorkerOut(BaseModel):
    """Field assistant (field staff) as returned in list/detail. Includes user attributes."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="User/field assistant UUID.")
    name: str = Field(..., description="Full name.")
    email: str | None = Field(None, description="Email address.")
    designation: str = Field(..., description="Job designation.")
    phone: str = Field(..., description="Phone number.")
    address: str | None = Field(None, description="Address or location.")
    role: str | None = Field(None, description="fieldAssistant or fieldManager.")
    department_id: uuid.UUID | None = Field(None, description="Department UUID.")
    department_name: str | None = Field(None, description="Department name.")
    zone_id: uuid.UUID | None = Field(None, description="Zone UUID.")
    ward_id: uuid.UUID | None = Field(None, description="Ward UUID.")
    last_active_ward: str | None = Field(None, description="Last ward where the field assistant was active.")
    rating: float | None = Field(None, description="Field assistant rating.")
    tasks_completed: int = Field(0, description="Number of tasks completed.")
    tasks_active: int = Field(0, description="Number of active tasks.")
    status: str | None = Field(None, description="onDuty or offDuty.")
    last_active_lat: float | None = Field(None, description="Last known latitude.")
    last_active_lng: float | None = Field(None, description="Last known longitude.")

    @field_validator("tasks_completed", "tasks_active", mode="before")
    @classmethod
    def coerce_none_to_zero(cls, v: int | None) -> int:
        return 0 if v is None else v


class WorkerListResponse(BaseModel):
    """Paginated list of field assistants."""

    items: list[WorkerOut] = Field(..., description="List of field assistants.")
    total: int = Field(..., description="Total count matching the filter.")
