"""
Tests for weather/cache.py — mocks the HTTP client and state manager.
No network or disk I/O needed.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from rain_sensor.weather.cache import WeatherCache
from rain_sensor.weather.client import WeatherFetchError


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_forecast(hourly_count: int = 3) -> dict:
    now_unix = int(datetime.now(timezone.utc).timestamp())
    return {
        "hourly": [
            {"dt": now_unix + i * 3600, "pop": 0.1, "rain": {"1h": 0.5}}
            for i in range(hourly_count)
        ],
        "daily": [{"pop": 0.1}],
    }


def _make_state(age_minutes: float | None = None, cached: dict | None = None):
    state = MagicMock()
    state.get_cached_forecast_age_minutes.return_value = age_minutes
    state.get_cached_forecast.return_value = cached
    return state


# ── Cache hit ─────────────────────────────────────────────────────────────────

def test_returns_cached_when_fresh():
    cached = _make_forecast()
    state  = _make_state(age_minutes=10, cached=cached)
    wc     = WeatherCache(state, cache_ttl_minutes=30)

    with patch("rain_sensor.weather.cache.fetch_forecast") as mock_fetch:
        result = wc.get_forecast(0, 0, "key")
        mock_fetch.assert_not_called()

    assert result is cached


# ── Cache miss — fresh fetch ──────────────────────────────────────────────────

def test_fetches_when_cache_stale():
    fresh = _make_forecast()
    state = _make_state(age_minutes=60, cached=None)
    wc    = WeatherCache(state, cache_ttl_minutes=30)

    with patch("rain_sensor.weather.cache.fetch_forecast", return_value=fresh) as mock_fetch:
        result = wc.get_forecast(1.0, 2.0, "mykey")
        mock_fetch.assert_called_once_with(1.0, 2.0, "mykey")

    state.set_cached_forecast.assert_called_once_with(fresh)
    assert result is fresh


def test_fetches_when_no_cache_at_all():
    fresh = _make_forecast()
    state = _make_state(age_minutes=None, cached=None)
    wc    = WeatherCache(state, cache_ttl_minutes=30)

    with patch("rain_sensor.weather.cache.fetch_forecast", return_value=fresh):
        result = wc.get_forecast(0, 0, "key")

    assert result is fresh


# ── Fallback on API error ─────────────────────────────────────────────────────

def test_falls_back_to_stale_cache_on_error():
    stale = _make_forecast()
    state = _make_state(age_minutes=120, cached=stale)
    wc    = WeatherCache(state, cache_ttl_minutes=30)

    with patch("rain_sensor.weather.cache.fetch_forecast", side_effect=WeatherFetchError("timeout")):
        result = wc.get_forecast(0, 0, "key")

    assert result is stale


def test_raises_when_api_fails_and_no_cache():
    state = _make_state(age_minutes=None, cached=None)
    wc    = WeatherCache(state, cache_ttl_minutes=30)

    with patch("rain_sensor.weather.cache.fetch_forecast", side_effect=WeatherFetchError("fail")):
        with pytest.raises(WeatherFetchError):
            wc.get_forecast(0, 0, "key")


# ── Rainfall accumulation ─────────────────────────────────────────────────────

def test_accumulates_rainfall_on_fresh_fetch():
    fresh = _make_forecast(hourly_count=2)
    state = _make_state(age_minutes=None, cached=None)
    wc    = WeatherCache(state, cache_ttl_minutes=30)

    with patch("rain_sensor.weather.cache.fetch_forecast", return_value=fresh):
        wc.get_forecast(0, 0, "key")

    # upsert_rainfall_records should be called with 2 records
    call_args = state.upsert_rainfall_records.call_args[0][0]
    assert len(call_args) == 2
    assert all(r["mm"] == pytest.approx(0.5) for r in call_args)


def test_records_zero_mm_for_hours_without_rain():
    now_unix = int(datetime.now(timezone.utc).timestamp())
    fresh = {"hourly": [{"dt": now_unix, "pop": 0.1}], "daily": []}  # no rain key
    state = _make_state(age_minutes=None, cached=None)
    wc    = WeatherCache(state, cache_ttl_minutes=30)

    with patch("rain_sensor.weather.cache.fetch_forecast", return_value=fresh):
        wc.get_forecast(0, 0, "key")

    records = state.upsert_rainfall_records.call_args[0][0]
    assert records[0]["mm"] == pytest.approx(0.0)
