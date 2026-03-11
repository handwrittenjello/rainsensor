"""
Persistent state manager.

All mutable runtime state is stored in a single JSON file so it survives
process restarts. This includes:
  - Cached OWM forecast response + fetch timestamp
  - Rolling hourly rainfall history (last 48 h, upserted by `dt`)
  - Last relay state ("allowed" | "suppressed")
  - Manual override flag
  - Decision log (last 35 days of check_and_set() results)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_RAINFALL_KEEP_HOURS  = 48
_DECISION_KEEP_DAYS   = 35   # keep a bit more than 30 for chart margin


class StateManager:
    def __init__(self, state_file: str) -> None:
        self._path = Path(state_file)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open() as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not read state file (%s) — starting fresh: %s", self._path, exc)
            return {}

    def save(self, data: dict[str, Any]) -> None:
        try:
            with self._path.open("w") as f:
                json.dump(data, f, indent=2)
        except OSError as exc:
            log.error("Could not write state file (%s): %s", self._path, exc)

    def _update(self, updates: dict[str, Any]) -> None:
        data = self.load()
        data.update(updates)
        self.save(data)

    # ── Forecast cache ────────────────────────────────────────────────────────

    def get_cached_forecast(self) -> Optional[dict]:
        return self.load().get("cached_forecast")

    def get_cached_forecast_age_minutes(self) -> Optional[float]:
        data = self.load()
        fetched_at = data.get("cached_forecast_fetched_at")
        if not fetched_at:
            return None
        fetched_dt = datetime.fromisoformat(fetched_at)
        now = datetime.now(timezone.utc)
        return (now - fetched_dt).total_seconds() / 60.0

    def set_cached_forecast(self, forecast: dict) -> None:
        self._update({
            "cached_forecast": forecast,
            "cached_forecast_fetched_at": datetime.now(timezone.utc).isoformat(),
        })

    # ── Rainfall history ──────────────────────────────────────────────────────

    def get_rainfall_history(self) -> list[dict]:
        """Returns list of {ts: ISO str, dt: int, mm: float} records."""
        return self.load().get("rainfall_history", [])

    def upsert_rainfall_records(self, records: list[dict]) -> None:
        """
        Upsert hourly rainfall records keyed by OWM `dt` (Unix epoch).
        A record is: {"dt": int, "ts": ISO str, "mm": float}
        Existing entries with the same dt are overwritten (no double-counting
        when the same hour appears in two consecutive fetches).
        """
        data = self.load()
        existing: dict[int, dict] = {
            r["dt"]: r for r in data.get("rainfall_history", [])
        }
        for rec in records:
            existing[rec["dt"]] = rec
        data["rainfall_history"] = list(existing.values())
        self.save(data)

    def trim_rainfall_history(self) -> None:
        """Drop records older than _RAINFALL_KEEP_HOURS."""
        data = self.load()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=_RAINFALL_KEEP_HOURS)
        kept = [
            r for r in data.get("rainfall_history", [])
            if datetime.fromisoformat(r["ts"]) >= cutoff
        ]
        data["rainfall_history"] = kept
        self.save(data)

    def get_recent_rainfall_mm(self, hours: int = 24) -> float:
        """Sum rainfall records from the past *hours* hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        total = 0.0
        for rec in self.get_rainfall_history():
            try:
                ts = datetime.fromisoformat(rec["ts"])
                if ts >= cutoff:
                    total += float(rec.get("mm", 0.0))
            except (KeyError, ValueError):
                continue
        return total

    # ── Relay state ───────────────────────────────────────────────────────────

    def get_relay_state(self) -> Optional[str]:
        """Returns "suppressed", "allowed", or None if never set."""
        return self.load().get("relay_state")

    def set_relay_state(self, state: str) -> None:
        self._update({"relay_state": state})

    # ── Manual override ───────────────────────────────────────────────────────

    def get_manual_override(self) -> Optional[str]:
        """Returns "suppress", "allow", or None (= automatic)."""
        return self.load().get("manual_override")

    def set_manual_override(self, action: str) -> None:
        self._update({"manual_override": action})

    def clear_manual_override(self) -> None:
        data = self.load()
        data.pop("manual_override", None)
        self.save(data)

    # ── Decision log ──────────────────────────────────────────────────────────

    def append_decision(self, decision_record: dict) -> None:
        """
        Append a decision record and trim to _DECISION_KEEP_DAYS days.
        Expected keys: ts, suppress, reasons, pop_max, forecast_rain_mm, recent_rain_mm
        """
        data = self.load()
        log_entries: list[dict] = data.get("decision_log", [])
        log_entries.append(decision_record)

        cutoff = datetime.now(timezone.utc) - timedelta(days=_DECISION_KEEP_DAYS)
        log_entries = [
            e for e in log_entries
            if datetime.fromisoformat(e["ts"]) >= cutoff
        ]
        data["decision_log"] = log_entries
        self.save(data)

    def get_decision_log(self, days: int = 30) -> list[dict]:
        """Return decision records from the last *days* days, oldest first."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return [
            e for e in self.load().get("decision_log", [])
            if datetime.fromisoformat(e["ts"]) >= cutoff
        ]
