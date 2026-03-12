"""
Scheduler and core check-and-set loop.

check_and_set() is the single function that:
  1. Honours any active manual override.
  2. Fetches (or reuses cached) OWM forecast.
  3. Evaluates suppression criteria.
  4. Applies relay state.
  5. Persists the decision to state.json for the dashboard.

start_scheduler() wraps it in a schedule-library loop that blocks forever,
firing at the times listed in config.schedule.times.
"""

from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone

import schedule

from rain_sensor.config import Config
from rain_sensor.decision import Decision, evaluate
from rain_sensor.relay.base import RelayBackend
from rain_sensor.state import StateManager
from rain_sensor.weather.cache import WeatherCache
from rain_sensor.weather.client import WeatherFetchError

log = logging.getLogger(__name__)


def check_and_set(
    config: Config,
    relay: RelayBackend,
    state: StateManager,
    cache: WeatherCache,
) -> Decision | None:
    """
    Run one weather-check cycle and update the relay accordingly.

    Returns the Decision that was made, or None if a manual override is active.
    """
    # ── Manual override guard ─────────────────────────────────────────────────
    override = state.get_manual_override()
    if override:
        log.info("Manual override active (%s) — skipping automatic check", override)
        return None

    # ── Fetch forecast ────────────────────────────────────────────────────────
    try:
        forecast = cache.get_forecast(config.lat, config.lon, config.owm_api_key)
    except WeatherFetchError as exc:
        log.error("Weather fetch failed and no cache available: %s", exc)
        log.warning("Fail-safe: energizing relay (allow watering — open SEN circuit)")
        relay.allow_watering()
        state.set_relay_state("allowed")
        return None

    recent_rain = state.get_recent_rainfall_mm(hours=24)

    # ── Evaluate ──────────────────────────────────────────────────────────────
    decision = evaluate(
        forecast=forecast,
        recent_rain_mm=recent_rain,
        rain_probability_pct=config.thresholds.rain_probability_pct,
        rain_probability_hours=config.thresholds.rain_probability_hours,
        forecast_rain_mm_threshold=config.thresholds.forecast_rain_mm,
        recent_rain_mm_threshold=config.thresholds.recent_rain_mm,
    )

    # ── Log all reasons ───────────────────────────────────────────────────────
    for reason in decision.reasons:
        log.info("  %s", reason)

    # ── Apply relay state ─────────────────────────────────────────────────────
    if decision.suppress:
        log.info("DECISION: Suppress watering — de-energizing relay (closing NC, shorting SEN)")
        relay.suppress_watering()
        state.set_relay_state("suppressed")
    else:
        log.info("DECISION: Allow watering — energizing relay (opening NC, releasing SEN)")
        relay.allow_watering()
        state.set_relay_state("allowed")

    # ── Persist decision log (for web dashboard history chart) ────────────────
    state.append_decision({
        "ts":               datetime.now(timezone.utc).isoformat(),
        "suppress":         decision.suppress,
        "reasons":          decision.reasons,
        "pop_max":          round(decision.pop_max, 3),
        "forecast_rain_mm": round(decision.forecast_rain_mm, 2),
        "recent_rain_mm":   round(decision.recent_rain_mm, 2),
    })

    return decision


def start_scheduler(
    config: Config,
    relay: RelayBackend,
    state: StateManager,
    cache: WeatherCache,
) -> None:
    """
    Start the blocking schedule loop. Runs check_and_set() at each time
    in config.schedule.times. Handles SIGTERM for clean shutdown.
    """
    _running = [True]

    def _shutdown(signum, frame):   # noqa: ARG001
        log.info("SIGTERM received — shutting down scheduler")
        _running[0] = False

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    def _job():
        log.info("=== Scheduled weather check ===")
        check_and_set(config, relay, state, cache)

    for t in config.schedule.times:
        schedule.every().day.at(t).do(_job)
        log.info("Scheduled weather check at %s daily", t)

    if config.schedule.run_on_start:
        log.info("run_on_start=true — running initial check now")
        _job()

    log.info("Scheduler running. Press Ctrl+C to stop.")
    while _running[0]:
        schedule.run_pending()
        time.sleep(30)

    log.info("Scheduler stopped.")
