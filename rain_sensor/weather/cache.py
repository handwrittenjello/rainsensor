"""
Weather cache and rainfall accumulation.

Wraps weather.client.fetch_forecast with:
  1. TTL-based disk-backed caching (survives process restarts)
  2. Rainfall history accumulation from hourly data

Caching strategy:
  - On each get_forecast() call, check the stored fetch timestamp.
  - If the cached data is younger than cache_ttl_minutes, return it without
    making an HTTP request.
  - On a fresh fetch, immediately persist to state.json (layer 2 cache) so
    a crash-restart cycle within the TTL window avoids a redundant API call.
  - On API error, fall back to cached data regardless of TTL if available,
    to avoid letting a transient network blip change the relay state.

Rainfall accumulation:
  - Each fresh fetch extracts hourly rain.1h values.
  - Records are upserted into state by their OWM `dt` timestamp (Unix epoch).
  - This prevents double-counting when the same hour appears in two fetches.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from rain_sensor.state import StateManager
from rain_sensor.weather.client import fetch_forecast, WeatherFetchError

log = logging.getLogger(__name__)


class WeatherCache:
    def __init__(self, state: StateManager, cache_ttl_minutes: int = 30) -> None:
        self._state = state
        self._ttl   = cache_ttl_minutes

    def get_forecast(self, lat: float, lon: float, api_key: str) -> dict:
        """
        Return a forecast dict. Fetches fresh data only when the cache is
        stale or empty. Falls back to cached data on API errors.
        """
        age = self._state.get_cached_forecast_age_minutes()

        if age is not None and age < self._ttl:
            log.debug("Using cached forecast (age=%.1f min < TTL=%d min)", age, self._ttl)
            return self._state.get_cached_forecast()

        log.info("Fetching fresh forecast from OpenWeatherMap")
        try:
            fresh = fetch_forecast(lat, lon, api_key)
            self._state.set_cached_forecast(fresh)
            self._accumulate_rainfall(fresh.get("hourly", []))
            return fresh
        except WeatherFetchError as exc:
            log.warning("OWM fetch failed: %s", exc)
            cached = self._state.get_cached_forecast()
            if cached:
                log.warning("Falling back to stale cached forecast")
                return cached
            raise

    def _accumulate_rainfall(self, hourly: list[dict]) -> None:
        """
        Extract rain.1h from each hourly entry and upsert into state.
        Records that have no rain (key absent or 0) are stored as 0.0 so
        get_recent_rainfall_mm() has a complete picture.
        """
        records = []
        for entry in hourly:
            dt = entry.get("dt")
            if dt is None:
                continue
            mm = entry.get("rain", {}).get("1h", 0.0)
            ts = datetime.fromtimestamp(dt, tz=timezone.utc).isoformat()
            records.append({"dt": dt, "ts": ts, "mm": mm})

        if records:
            self._state.upsert_rainfall_records(records)
            self._state.trim_rainfall_history()
            log.debug("Accumulated %d hourly rainfall records", len(records))
