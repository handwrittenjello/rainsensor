"""
Flask web dashboard for the Rain Sensor Bypass Controller.

Routes:
  GET  /                → full dashboard page
  GET  /api/status      → JSON: relay state, last decision, override, recent rain
  GET  /api/forecast    → JSON: next 6 hourly entries (pop, rain, dt)
  GET  /api/history     → JSON: last 30 days of Decision log entries
  POST /api/override    → JSON body: {"action": "suppress"|"allow"|"clear"}
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from flask import Flask, jsonify, render_template, request, abort

from rain_sensor.config import Config
from rain_sensor.relay.base import RelayBackend
from rain_sensor.state import StateManager
from rain_sensor.weather.cache import WeatherCache

log = logging.getLogger(__name__)

_MM_TO_IN = 0.0393701   # millimetres → inches


def create_app(
    config: Config,
    state: StateManager,
    relay: RelayBackend,
    cache: WeatherCache,
) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = "rain-sensor-local"   # local-only, no auth needed

    # ── Main dashboard ────────────────────────────────────────────────────────

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            lat=config.lat,
            lon=config.lon,
            # API key exposed to JS only for OWM map tiles (read-only, tile requests only)
            owm_api_key=config.owm_api_key,
        )

    # ── API: current status (polled by HTMX every 60 s) ──────────────────────

    @app.route("/api/status")
    def api_status():
        data           = state.load()
        relay_state    = data.get("relay_state", "unknown")
        override       = data.get("manual_override")
        last           = state.get_last_decision()
        recent_rain_mm = state.get_recent_rainfall_mm(hours=24)
        cache_age      = state.get_cached_forecast_age_minutes()

        return jsonify({
            "relay_state":    relay_state,
            "override":       override,
            "recent_rain_in": round(recent_rain_mm * _MM_TO_IN, 3),
            "cache_age_min":  round(cache_age, 1) if cache_age is not None else None,
            "last_check": {
                "ts":               last["ts"]                                          if last else None,
                "suppress":         last["suppress"]                                    if last else None,
                "reasons":          last.get("reasons", [])                             if last else [],
                "pop_max_pct":      round(last["pop_max"] * 100)                        if last else None,
                "forecast_rain_in": round(last["forecast_rain_mm"] * _MM_TO_IN, 3)     if last else None,
            },
        })

    # ── API: next 6 hourly entries ────────────────────────────────────────────

    @app.route("/api/forecast")
    def api_forecast():
        cached = state.get_cached_forecast()
        if not cached:
            return jsonify({"hourly": []})

        hourly_raw = cached.get("hourly", [])[:6]
        hourly = []
        for h in hourly_raw:
            dt = h.get("dt", 0)
            ts = datetime.fromtimestamp(dt, tz=timezone.utc).strftime("%H:%M")
            hourly.append({
                "ts":       ts,
                "pop_pct":  round(h.get("pop", 0.0) * 100),
                "rain_in":  round(h.get("rain", {}).get("1h", 0.0) * _MM_TO_IN, 3),
                "temp_f":   round(h.get("temp", 0.0), 1),
                "desc":     h.get("weather", [{}])[0].get("description", ""),
            })
        return jsonify({"hourly": hourly})

    # ── API: 30-day decision history ──────────────────────────────────────────

    @app.route("/api/history")
    def api_history():
        entries = state.get_decision_log(days=30)

        # Aggregate by calendar date (UTC) for the bar chart
        by_date: dict[str, dict] = {}
        for e in entries:
            date_str = e["ts"][:10]   # "YYYY-MM-DD"
            if date_str not in by_date:
                by_date[date_str] = {"date": date_str, "suppressed": 0, "allowed": 0}
            if e.get("suppress"):
                by_date[date_str]["suppressed"] += 1
            else:
                by_date[date_str]["allowed"] += 1

        # Fill in missing days in the past 30 days with zeros
        today = datetime.now(timezone.utc).date()
        result = []
        for i in range(29, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            result.append(by_date.get(d, {"date": d, "suppressed": 0, "allowed": 0}))

        return jsonify({"history": result})

    # ── API v1: comprehensive status for external dashboards ─────────────────

    @app.route("/api/v1/status")
    def api_v1_status():
        """
        Public read-only endpoint for external dashboards and integrations.

        Returns a single JSON object with:
          relay          — current physical relay state and what it means
          override       — manual override info
          rainfall       — accumulated totals for 24 h / 7 d / 30 d (inches)
          forecast       — next 6 hourly OWM entries
          last_decision  — most recent automatic check result
          thresholds     — configured suppression thresholds
          cache          — age of the OWM forecast cache
        """
        data           = state.load()
        relay_state    = data.get("relay_state", "unknown")
        override       = data.get("manual_override")
        last           = state.get_last_decision()
        cache_age      = state.get_cached_forecast_age_minutes()

        rain_24h_mm  = state.get_recent_rainfall_mm(hours=24)
        rain_7d_mm   = state.get_recent_rainfall_mm(hours=7 * 24)
        rain_30d_mm  = state.get_recent_rainfall_mm(hours=30 * 24)

        # Hourly forecast (next 6 h)
        cached_fc   = state.get_cached_forecast() or {}
        hourly_raw  = cached_fc.get("hourly", [])[:6]
        hourly_out  = []
        for h in hourly_raw:
            dt = h.get("dt", 0)
            hourly_out.append({
                "time_utc":  datetime.fromtimestamp(dt, tz=timezone.utc).isoformat(),
                "pop_pct":   round(h.get("pop", 0.0) * 100),
                "rain_in":   round(h.get("rain", {}).get("1h", 0.0) * _MM_TO_IN, 3),
                "temp_f":    round(h.get("temp", 0.0), 1),
                "desc":      h.get("weather", [{}])[0].get("description", ""),
            })

        return jsonify({
            "relay": {
                "state":            relay_state,             # "suppressed" | "allowed" | "unknown"
                "watering_active":  relay_state != "suppressed",
            },
            "override": {
                "active":  override is not None,
                "mode":    override,                         # "suppress" | "allow" | null
            },
            "rainfall": {
                "last_24h_in":  round(rain_24h_mm  * _MM_TO_IN, 3),
                "last_7d_in":   round(rain_7d_mm   * _MM_TO_IN, 3),
                "last_30d_in":  round(rain_30d_mm  * _MM_TO_IN, 3),
            },
            "forecast": hourly_out,
            "last_decision": {
                "ts":               last["ts"]                                       if last else None,
                "suppress":         last["suppress"]                                 if last else None,
                "reasons":          last.get("reasons", [])                          if last else [],
                "pop_max_pct":      round(last["pop_max"] * 100)                     if last else None,
                "forecast_rain_in": round(last["forecast_rain_mm"] * _MM_TO_IN, 3)  if last else None,
                "recent_rain_in":   round(last["recent_rain_mm"]   * _MM_TO_IN, 3)  if last else None,
            },
            "thresholds": {
                "rain_probability_pct":   config.thresholds.rain_probability_pct,
                "rain_probability_hours": config.thresholds.rain_probability_hours,
                "forecast_rain_in":       round(config.thresholds.forecast_rain_mm * _MM_TO_IN, 3),
                "recent_rain_in":         round(config.thresholds.recent_rain_mm   * _MM_TO_IN, 3),
            },
            "cache_age_min": round(cache_age, 1) if cache_age is not None else None,
        })

    # ── API: force weather check ──────────────────────────────────────────────

    @app.route("/api/check", methods=["POST"])
    def api_check():
        from rain_sensor.scheduler import check_and_set
        log.info("Web UI: forced weather check requested")
        decision = check_and_set(config, relay, state, cache)
        return jsonify({
            "ok": True,
            "relay_state": state.get_relay_state(),
            "suppress": decision.suppress if decision else None,
            "reasons": decision.reasons if decision else ["Manual override active — check skipped"],
        })

    # ── API: manual override ──────────────────────────────────────────────────

    @app.route("/api/override", methods=["POST"])
    def api_override():
        body = request.get_json(force=True, silent=True) or {}
        action = body.get("action", "").strip().lower()

        if action == "suppress":
            relay.suppress_watering()
            state.set_relay_state("suppressed")
            state.set_manual_override("suppress")
            log.info("Web UI: manual override → suppress")
            return jsonify({"ok": True, "relay_state": "suppressed"})

        elif action == "allow":
            relay.allow_watering()
            state.set_relay_state("allowed")
            state.set_manual_override("allow")
            log.info("Web UI: manual override → allow")
            return jsonify({"ok": True, "relay_state": "allowed"})

        elif action == "clear":
            state.clear_manual_override()
            log.info("Web UI: manual override cleared — running immediate weather check")
            from rain_sensor.scheduler import check_and_set
            check_and_set(config, relay, state, cache)
            return jsonify({"ok": True, "relay_state": state.get_relay_state()})

        else:
            abort(400, f"Unknown action: {action!r}. Expected 'suppress', 'allow', or 'clear'.")

    return app
