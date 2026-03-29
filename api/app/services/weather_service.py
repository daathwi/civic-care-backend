"""
Ward weather & air quality via Open-Meteo (free, no API key).
Uses ward centroid (lat, lng) for location-based data.
Falls back to mock data when external API is unreachable (e.g. DNS/network).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

_log = logging.getLogger(__name__)

# Open-Meteo endpoints (no auth required)
# Note: host must be air-quality-api.open-meteo.com (hyphens). "air-quality.api.open-meteo.com" does not resolve.
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Cache TTL seconds (15 min)
CACHE_TTL = 900
_cache: dict[tuple[str, float, float], tuple[float, dict[str, Any]]] = {}


def _cache_key(prefix: str, lat: float, lng: float) -> tuple[str, float, float]:
    """Round to 2 decimals for cache key (≈1km precision)."""
    return (prefix, round(lat, 2), round(lng, 2))


def _mock_air_quality() -> dict[str, Any]:
    """Fallback when Open-Meteo is unreachable (DNS/network)."""
    now = datetime.now(timezone.utc)
    times = [(now.replace(hour=h, minute=0, second=0, microsecond=0)).strftime("%Y-%m-%dT%H:%M") for h in range(24)]
    return {
        "latitude": 28.61,
        "longitude": 77.21,
        "hourly": {
            "time": times,
            "pm10": [45.0] * 24,
            "pm2_5": [25.0] * 24,
            "us_aqi_pm2_5": [75] * 24,
            "nitrogen_dioxide": [20.0] * 24,
            "ozone": [50.0] * 24,
        },
    }


def _mock_weather() -> dict[str, Any]:
    """Fallback when Open-Meteo is unreachable."""
    now = datetime.now(timezone.utc)
    times = [(now.replace(hour=h, minute=0, second=0, microsecond=0)).strftime("%Y-%m-%dT%H:%M") for h in range(24)]
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    dates = [(base + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(7)]
    return {
        "latitude": 28.61,
        "longitude": 77.21,
        "current": {
            "temperature_2m": 32.0,
            "relative_humidity_2m": 55,
            "apparent_temperature": 34.0,
            "weather_code": 1,
            "wind_speed_10m": 12.0,
            "wind_direction_10m": 180,
            "wind_gusts_10m": 18.0,
            "pressure_msl": 1013.0,
            "cloud_cover": 25,
            "is_day": 1,
        },
        "hourly": {
            "time": times,
            "temperature_2m": [32.0] * 24,
            "relative_humidity_2m": [55] * 24,
            "precipitation_probability": [10] * 24,
            "precipitation": [0.0] * 24,
            "weather_code": [1] * 24,
            "wind_speed_10m": [12.0] * 24,
            "cloud_cover": [25] * 24,
            "visibility": [10000.0] * 24,
        },
        "daily": {
            "time": dates,
            "weather_code": [1] * 7,
            "temperature_2m_max": [35.0, 34.0, 33.0, 34.0, 35.0, 34.0, 33.0],
            "temperature_2m_min": [26.0, 25.0, 25.0, 26.0, 26.0, 25.0, 25.0],
            "sunrise": [(base + timedelta(days=d)).strftime("%Y-%m-%d") + "T06:00" for d in range(7)],
            "sunset": [(base + timedelta(days=d)).strftime("%Y-%m-%d") + "T18:30" for d in range(7)],
            "uv_index_max": [8.0, 7.5, 7.0, 8.0, 8.5, 7.5, 7.0],
            "precipitation_sum": [0.0] * 7,
            "precipitation_probability_max": [10, 20, 5, 15, 5, 10, 20],
            "wind_speed_10m_max": [15.0] * 7,
        },
    }


async def fetch_air_quality(lat: float, lng: float) -> dict[str, Any]:
    """Return localized (mocked) air quality data instantly."""
    return _mock_air_quality()


async def fetch_weather(lat: float, lng: float) -> dict[str, Any]:
    """Return localized (mocked) weather forecast data instantly."""
    return _mock_weather()


async def fetch_ward_weather(lat: float, lng: float) -> dict[str, Any]:
    """
    Fetch combined air quality + weather from local mocks.
    """
    return {
        "air_quality": _mock_air_quality(),
        "weather": _mock_weather()
    }
