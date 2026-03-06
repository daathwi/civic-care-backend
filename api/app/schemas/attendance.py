from __future__ import annotations

import uuid
import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ClockInRequest(BaseModel):
    """Request body for clock-in. Access: fieldManager, fieldAssistant, or admin."""

    lat: Decimal = Field(..., description="Latitude at clock-in location.")
    lng: Decimal = Field(..., description="Longitude at clock-in location.")


class ClockOutRequest(BaseModel):
    """Request body for clock-out. Access: fieldManager, fieldAssistant, or admin."""

    lat: Decimal = Field(..., description="Latitude at clock-out location.")
    lng: Decimal = Field(..., description="Longitude at clock-out location.")


class AttendanceOut(BaseModel):
    """Attendance record (one clock-in/out per day)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Record UUID.")
    user_id: uuid.UUID = Field(..., description="User (worker) UUID.")
    date: dt.date = Field(..., description="Date (YYYY-MM-DD).")
    clock_in_time: dt.datetime = Field(..., description="Clock-in time.")
    clock_in_lat: Decimal = Field(..., description="Clock-in latitude.")
    clock_in_lng: Decimal = Field(..., description="Clock-in longitude.")
    clock_out_time: dt.datetime | None = Field(None, description="Clock-out time (null if still clocked in).")
    clock_out_lat: Decimal | None = Field(None, description="Clock-out latitude.")
    clock_out_lng: Decimal | None = Field(None, description="Clock-out longitude.")
    total_duration_seconds: int | None = Field(None, description="Total seconds between clock-in and clock-out.")


class AttendanceStatusOut(BaseModel):
    """Current attendance status for the authenticated user."""

    is_clocked_in: bool = Field(..., description="True if the user has an active clock-in today.")
    current_record: AttendanceOut | None = Field(None, description="Today's attendance record if clocked in.")
