from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PoliticalPartyOut(BaseModel):
    """Political party for ward representatives."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Party UUID.")
    name: str = Field(..., description="Party full name.")
    short_code: str | None = Field(None, description="Party short code (e.g. BJP, AAP).")
    color: str | None = Field(None, description="Hex color for charts (e.g. #FF6600).")


class PoliticalPartyCreate(BaseModel):
    """Request body for creating a political party."""

    name: str = Field(..., min_length=1, description="Party full name.")
    short_code: str | None = Field(None, description="Party short code.")
    color: str | None = Field(None, description="Hex color for charts.")


class PoliticalPartyUpdate(BaseModel):
    """Request body for updating a political party."""

    name: str | None = Field(None, description="Party full name.")
    short_code: str | None = Field(None, description="Party short code.")
    color: str | None = Field(None, description="Hex color for charts.")


class ZoneOut(BaseModel):
    """Zone (administrative area) as returned in list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Zone UUID.")
    name: str = Field(..., description="Zone name.")
    code: str = Field(..., description="Zone code (e.g. CE, SO).")


class ZoneCreate(BaseModel):
    """Request body for creating a zone. Access: fieldManager or admin."""

    name: str = Field(..., description="Zone name.")
    code: str = Field(..., description="Unique zone code.")


class ZoneUpdate(BaseModel):
    """Request body for updating a zone. Access: fieldManager or admin."""

    name: str | None = Field(None, description="Zone name.")
    code: str | None = Field(None, description="Unique zone code.")


class WardOut(BaseModel):
    """Ward as returned in list/lookup responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Ward UUID.")
    name: str = Field(..., description="Ward name.")
    number: int = Field(..., description="Ward number within the zone.")
    zone_id: uuid.UUID | None = Field(None, description="Zone UUID.")
    zone_name: str | None = Field(None, description="Zone name.")
    representative_name: str | None = Field(None, description="Ward representative name.")
    representative_phone: list[str] = Field(default_factory=list, description="Ward representative phone numbers.")
    party_id: uuid.UUID | None = Field(None, description="Political party UUID.")
    representative_party: str | None = Field(None, description="Party name (from party_id or legacy representative_party).")
    representative_email: str | None = Field(None, description="Ward representative email.")
    centroid_lat: float | None = Field(None, description="Centroid latitude of the ward polygon.")
    centroid_lng: float | None = Field(None, description="Centroid longitude of the ward polygon.")
    min_lat: float | None = Field(None, description="Minimum latitude of the ward bounds.")
    max_lat: float | None = Field(None, description="Maximum latitude of the ward bounds.")
    min_lng: float | None = Field(None, description="Minimum longitude of the ward bounds.")
    max_lng: float | None = Field(None, description="Maximum longitude of the ward bounds.")

    @field_validator("representative_phone", mode="before")
    @classmethod
    def empty_list_if_none(cls, v: list[str] | None) -> list[str]:
        return v if v is not None else []


class WardCreate(BaseModel):
    """Request body for creating a ward. Access: fieldManager or admin."""

    zone_id: uuid.UUID = Field(..., description="Zone UUID.")
    name: str = Field(..., description="Ward name.")
    number: int = Field(..., description="Ward number (unique within zone).")
    representative_name: str = Field(..., min_length=1, description="Ward representative name (required).")
    representative_phone: list[str] = Field(..., min_length=1, description="Ward representative phone numbers (at least one required).")
    party_id: uuid.UUID | None = Field(None, description="Political party UUID.")
    representative_email: str | None = Field(None, description="Ward representative email.")

    @field_validator("representative_phone", mode="before")
    @classmethod
    def normalize_phone_list(cls, v: list[str] | str | None) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            v = [p.strip() for p in v.replace(",", " ").split() if p.strip()]
        return [str(p).strip() for p in v if str(p).strip()]


class WardUpdate(BaseModel):
    """Request body for updating a ward. Access: fieldManager or admin."""

    zone_id: uuid.UUID | None = Field(None, description="Zone UUID.")
    name: str | None = Field(None, description="Ward name.")
    number: int | None = Field(None, description="Ward number (unique within zone).")
    representative_name: str | None = Field(None, description="Ward representative name.")
    representative_phone: list[str] | None = Field(None, description="Ward representative phone numbers.")
    party_id: uuid.UUID | None = Field(None, description="Political party UUID.")
    representative_email: str | None = Field(None, description="Ward representative email.")


class WardLookupResult(BaseModel):
    """Result of ward lookup by coordinates."""

    ward: WardOut | None = Field(None, description="Ward if found; null otherwise.")
    found: bool = Field(..., description="True if a ward contains the given lat/lng.")


class DepartmentCategoryOut(BaseModel):
    """Grievance category under a department."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Category UUID.")
    name: str = Field(..., description="Category name.")
    dept_id: uuid.UUID = Field(..., description="Department UUID.")


class GrievanceCategoryCreate(BaseModel):
    """Request body for creating a grievance category. Access: fieldManager or admin."""

    name: str = Field(..., description="Category name.")


class GrievanceCategoryUpdate(BaseModel):
    """Request body for updating a category. Access: fieldManager or admin."""

    name: str | None = Field(None, description="Category name.")


class CategoryListOut(BaseModel):
    """Grievance category with department name (for admin listing)."""

    id: uuid.UUID = Field(..., description="Category UUID.")
    name: str = Field(..., description="Category name.")
    dept_id: uuid.UUID = Field(..., description="Department UUID.")
    dept_name: str = Field(..., description="Department name.")
