"""
Suppression decision logic.

This is a pure function module — no I/O, no side effects, no hardware access.
It takes a forecast dict and some thresholds and returns a Decision describing
whether watering should be suppressed and why.

Being pure makes it trivial to unit test without a Pi, relay HAT, or network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_MM_TO_IN = 0.0393701


def _in(mm: float) -> str:
    return f"{mm * _MM_TO_IN:.2f} in"


@dataclass
class Decision:
    suppress: bool
    reasons: list[str]
    pop_max: float           = 0.0   # highest hourly PoP seen in the look-ahead window
    forecast_rain_mm: float  = 0.0   # sum of hourly rain.1h in the look-ahead window
    recent_rain_mm: float    = 0.0   # accumulated rainfall in the past 24 h


def evaluate(
    forecast: dict[str, Any],
    recent_rain_mm: float,
    rain_probability_pct: int   = 50,
    rain_probability_hours: int = 3,
    forecast_rain_mm_threshold: float = 2.5,
    recent_rain_mm_threshold: float   = 5.0,
) -> Decision:
    """
    Decide whether to suppress watering based on weather data.

    Parameters
    ----------
    forecast:
        Raw OWM One Call 3.0 response dict (must contain a 'hourly' list).
    recent_rain_mm:
        Total accumulated rainfall in the past 24 hours (from StateManager).
    rain_probability_pct:
        Suppress if max hourly PoP in the look-ahead window >= this value (0–100).
    rain_probability_hours:
        Number of hourly entries to inspect from the start of the forecast.
    forecast_rain_mm_threshold:
        Suppress if the total forecasted rain in the look-ahead window >= this mm.
    recent_rain_mm_threshold:
        Suppress if accumulated recent rainfall >= this mm.
    """
    hourly = forecast.get("hourly", [])
    window = hourly[:rain_probability_hours]

    reasons: list[str] = []
    suppress = False

    # ── Check 1: recent accumulated rainfall ──────────────────────────────────
    if recent_rain_mm >= recent_rain_mm_threshold:
        suppress = True
        reasons.append(
            f"Recent rainfall {_in(recent_rain_mm)} "
            f">= threshold {_in(recent_rain_mm_threshold)} in past 24 h"
        )

    # ── Check 2: forecast rain volume in look-ahead window ────────────────────
    forecast_total = sum(
        float(h.get("rain", {}).get("1h", 0.0)) for h in window
    )
    if forecast_total >= forecast_rain_mm_threshold:
        suppress = True
        reasons.append(
            f"Forecast rain {_in(forecast_total)} "
            f">= threshold {_in(forecast_rain_mm_threshold)} "
            f"in next {rain_probability_hours} h"
        )

    # ── Check 3: rain probability in look-ahead window ────────────────────────
    pop_values = [float(h.get("pop", 0.0)) for h in window]
    max_pop = max(pop_values) if pop_values else 0.0
    pop_threshold = rain_probability_pct / 100.0

    if max_pop >= pop_threshold:
        suppress = True
        reasons.append(
            f"Max rain probability {max_pop * 100:.0f}% "
            f">= threshold {rain_probability_pct}% "
            f"in next {rain_probability_hours} h"
        )

    if not suppress:
        reasons.append(
            f"No suppression criteria met — "
            f"PoP max {max_pop * 100:.0f}%, "
            f"forecast {_in(forecast_total)}, "
            f"recent {_in(recent_rain_mm)}"
        )

    return Decision(
        suppress=suppress,
        reasons=reasons,
        pop_max=max_pop,
        forecast_rain_mm=forecast_total,
        recent_rain_mm=recent_rain_mm,
    )
