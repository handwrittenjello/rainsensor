"""
OpenWeatherMap One Call API 3.0 client.

Single responsibility: make the HTTP request and return the raw response dict.
Caching, rainfall accumulation, and decision logic live elsewhere.

API docs: https://openweathermap.org/api/one-call-3

Fields used downstream:
  hourly[n].dt        — Unix epoch for the hour
  hourly[n].pop       — probability of precipitation (0.0–1.0)
  hourly[n].rain.1h   — rainfall in mm (key absent when 0)
  daily[0].rain       — total daily rainfall in mm (optional key)
  daily[0].pop        — daily precipitation probability
"""

from __future__ import annotations

import logging
from typing import Any

import requests

log = logging.getLogger(__name__)

_OWM_BASE = "https://api.openweathermap.org/data/3.0/onecall"
_TIMEOUT_SEC = 15


class WeatherFetchError(Exception):
    """Raised when the OWM API returns an unexpected response."""


def fetch_forecast(lat: float, lon: float, api_key: str) -> dict[str, Any]:
    """
    Fetch the current One Call 3.0 forecast for the given coordinates.

    Returns the raw JSON dict on success.
    Raises WeatherFetchError with a descriptive message on any failure.
    """
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": "imperial",
        "exclude": "minutely,alerts",
    }

    log.debug("Fetching OWM forecast: lat=%.4f lon=%.4f", lat, lon)

    try:
        resp = requests.get(_OWM_BASE, params=params, timeout=_TIMEOUT_SEC)
    except requests.exceptions.Timeout:
        raise WeatherFetchError("OWM request timed out after %ds" % _TIMEOUT_SEC)
    except requests.exceptions.ConnectionError as exc:
        raise WeatherFetchError(f"OWM connection error: {exc}")

    if resp.status_code == 401:
        raise WeatherFetchError(
            "OWM API key invalid or not activated yet (HTTP 401). "
            "Check your OWM_API_KEY in .env."
        )
    if resp.status_code == 429:
        raise WeatherFetchError(
            "OWM rate limit exceeded (HTTP 429). "
            "Using cached data if available."
        )
    if not resp.ok:
        raise WeatherFetchError(
            f"OWM returned HTTP {resp.status_code}: {resp.text[:200]}"
        )

    data = resp.json()
    log.debug(
        "OWM fetch OK — %d hourly entries, %d daily entries",
        len(data.get("hourly", [])),
        len(data.get("daily", [])),
    )
    return data
