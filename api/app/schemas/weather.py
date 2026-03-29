"""Schemas for ward weather & air quality API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WardWeatherOut(BaseModel):
    """Combined ward weather and air quality response."""

    ward_id: str = Field(..., description="Ward UUID.")
    ward_name: str = Field(..., description="Ward display name.")
    air_quality: dict[str, Any] = Field(
        ...,
        description="Open-Meteo air quality response (hourly pm10, pm2_5, us_aqi_pm2_5, etc.).",
    )
    weather: dict[str, Any] = Field(
        ...,
        description="Open-Meteo weather response (hourly temperature_2m, relative_humidity_2m, etc.).",
    )
