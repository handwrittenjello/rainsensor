"""
Tests for decision.py — no hardware or network needed.
"""

import pytest
from rain_sensor.decision import evaluate, Decision


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_forecast(hourly_entries: list[dict]) -> dict:
    return {"hourly": hourly_entries}


def _hour(pop: float = 0.0, rain_1h: float = 0.0) -> dict:
    h: dict = {"dt": 1700000000, "pop": pop}
    if rain_1h > 0:
        h["rain"] = {"1h": rain_1h}
    return h


# ── No suppression ────────────────────────────────────────────────────────────

def test_no_suppression_when_dry():
    forecast = _make_forecast([_hour(pop=0.1), _hour(pop=0.2), _hour(pop=0.1)])
    d = evaluate(forecast, recent_rain_mm=0.0)
    assert d.suppress is False
    assert d.pop_max == pytest.approx(0.2)
    assert d.forecast_rain_mm == pytest.approx(0.0)


# ── Rain probability trigger ──────────────────────────────────────────────────

def test_suppresses_on_high_pop():
    forecast = _make_forecast([_hour(pop=0.3), _hour(pop=0.7), _hour(pop=0.4)])
    d = evaluate(forecast, recent_rain_mm=0.0, rain_probability_pct=50)
    assert d.suppress is True
    assert d.pop_max == pytest.approx(0.7)
    assert any("probability" in r.lower() for r in d.reasons)


def test_does_not_suppress_when_pop_just_below_threshold():
    forecast = _make_forecast([_hour(pop=0.49)])
    d = evaluate(forecast, recent_rain_mm=0.0, rain_probability_pct=50)
    assert d.suppress is False


def test_suppresses_at_exact_pop_threshold():
    forecast = _make_forecast([_hour(pop=0.5)])
    d = evaluate(forecast, recent_rain_mm=0.0, rain_probability_pct=50)
    assert d.suppress is True


# ── Forecast rain volume trigger ──────────────────────────────────────────────

def test_suppresses_on_high_forecast_rain():
    forecast = _make_forecast([_hour(rain_1h=1.5), _hour(rain_1h=1.5)])
    d = evaluate(forecast, recent_rain_mm=0.0, forecast_rain_mm_threshold=2.5)
    assert d.suppress is True
    assert d.forecast_rain_mm == pytest.approx(3.0)
    assert any("forecast rain" in r.lower() for r in d.reasons)


def test_does_not_suppress_when_forecast_rain_below_threshold():
    forecast = _make_forecast([_hour(rain_1h=1.0), _hour(rain_1h=1.0)])
    d = evaluate(forecast, recent_rain_mm=0.0, forecast_rain_mm_threshold=2.5)
    assert d.suppress is False


# ── Recent rain trigger ───────────────────────────────────────────────────────

def test_suppresses_on_recent_rain():
    forecast = _make_forecast([_hour()])
    d = evaluate(forecast, recent_rain_mm=6.0, recent_rain_mm_threshold=5.0)
    assert d.suppress is True
    assert d.recent_rain_mm == pytest.approx(6.0)
    assert any("recent" in r.lower() for r in d.reasons)


def test_does_not_suppress_when_recent_rain_below_threshold():
    forecast = _make_forecast([_hour()])
    d = evaluate(forecast, recent_rain_mm=4.9, recent_rain_mm_threshold=5.0)
    assert d.suppress is False


# ── Multiple triggers ─────────────────────────────────────────────────────────

def test_multiple_reasons_reported():
    forecast = _make_forecast([_hour(pop=0.8, rain_1h=3.0)])
    d = evaluate(
        forecast,
        recent_rain_mm=6.0,
        rain_probability_pct=50,
        forecast_rain_mm_threshold=2.5,
        recent_rain_mm_threshold=5.0,
    )
    assert d.suppress is True
    assert len(d.reasons) == 3   # all three triggers fire


# ── Look-ahead window ─────────────────────────────────────────────────────────

def test_only_inspects_configured_window():
    # High PoP only in hour 4+ (outside the 3-hour window)
    forecast = _make_forecast([
        _hour(pop=0.1),
        _hour(pop=0.1),
        _hour(pop=0.1),
        _hour(pop=0.9),   # hour 4 — outside window
    ])
    d = evaluate(forecast, recent_rain_mm=0.0, rain_probability_pct=50, rain_probability_hours=3)
    assert d.suppress is False


# ── Empty forecast ────────────────────────────────────────────────────────────

def test_empty_forecast_no_suppression():
    d = evaluate({}, recent_rain_mm=0.0)
    assert d.suppress is False
    assert d.pop_max == pytest.approx(0.0)


# ── Return type ───────────────────────────────────────────────────────────────

def test_returns_decision_dataclass():
    d = evaluate({}, recent_rain_mm=0.0)
    assert isinstance(d, Decision)
    assert isinstance(d.reasons, list)
