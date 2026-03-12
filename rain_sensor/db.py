"""
SQLite database for persistent time-series data.

Tables:
  rainfall  — hourly accumulated rainfall in mm, keyed by OWM 'dt'
  decisions — all check_and_set() outcomes

The JSON state file continues to hold transient data:
  relay_state, manual_override, cached_forecast, cached_forecast_fetched_at
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path: str) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self._path))
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def _init_schema(self) -> None:
        with self._connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS rainfall (
                    dt  INTEGER PRIMARY KEY,
                    ts  TEXT    NOT NULL,
                    mm  REAL    NOT NULL DEFAULT 0.0
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts               TEXT    NOT NULL,
                    suppress         INTEGER NOT NULL,
                    reasons          TEXT    NOT NULL,
                    pop_max          REAL    DEFAULT 0.0,
                    forecast_rain_mm REAL    DEFAULT 0.0,
                    recent_rain_mm   REAL    DEFAULT 0.0
                );
                CREATE INDEX IF NOT EXISTS idx_rainfall_ts  ON rainfall(ts);
                CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
            """)
        log.debug("SQLite database ready: %s", self._path)

    # ── Rainfall ──────────────────────────────────────────────────────────────

    def upsert_rainfall(self, records: list[dict]) -> None:
        """Each record must have keys: dt (int), ts (ISO str), mm (float)."""
        with self._connect() as con:
            con.executemany(
                "INSERT OR REPLACE INTO rainfall (dt, ts, mm) VALUES (:dt, :ts, :mm)",
                records,
            )

    def get_recent_rainfall_mm(self, hours: int = 24) -> float:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._connect() as con:
            row = con.execute(
                "SELECT COALESCE(SUM(mm), 0.0) FROM rainfall WHERE ts >= ?",
                (cutoff,),
            ).fetchone()
        return float(row[0])

    def get_rainfall_by_day(self, days: int = 30) -> dict[str, float]:
        """Return {YYYY-MM-DD: total_mm} for the past N days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connect() as con:
            rows = con.execute(
                "SELECT substr(ts,1,10) AS day, SUM(mm) AS total "
                "FROM rainfall WHERE ts >= ? GROUP BY day ORDER BY day",
                (cutoff,),
            ).fetchall()
        return {r["day"]: float(r["total"]) for r in rows}

    # ── Decisions ─────────────────────────────────────────────────────────────

    def append_decision(self, record: dict) -> None:
        with self._connect() as con:
            con.execute(
                """INSERT INTO decisions
                   (ts, suppress, reasons, pop_max, forecast_rain_mm, recent_rain_mm)
                   VALUES (:ts, :suppress, :reasons, :pop_max, :forecast_rain_mm, :recent_rain_mm)""",
                {
                    "ts":               record["ts"],
                    "suppress":         int(record["suppress"]),
                    "reasons":          json.dumps(record.get("reasons", [])),
                    "pop_max":          record.get("pop_max", 0.0),
                    "forecast_rain_mm": record.get("forecast_rain_mm", 0.0),
                    "recent_rain_mm":   record.get("recent_rain_mm", 0.0),
                },
            )

    def get_decisions(self, days: int = 30) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connect() as con:
            rows = con.execute(
                """SELECT ts, suppress, reasons, pop_max, forecast_rain_mm, recent_rain_mm
                   FROM decisions WHERE ts >= ? ORDER BY ts""",
                (cutoff,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["suppress"] = bool(d["suppress"])
            d["reasons"]  = json.loads(d["reasons"])
            result.append(d)
        return result

    def get_last_decision(self) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                """SELECT ts, suppress, reasons, pop_max, forecast_rain_mm, recent_rain_mm
                   FROM decisions ORDER BY id DESC LIMIT 1"""
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["suppress"] = bool(d["suppress"])
        d["reasons"]  = json.loads(d["reasons"])
        return d

    # ── Migration from JSON state ─────────────────────────────────────────────

    def migrate_from_json(self, state_data: dict) -> None:
        """One-time import of rainfall and decisions from the old JSON state file."""
        rain_count = 0
        for rec in state_data.get("rainfall_history", []):
            try:
                self.upsert_rainfall([{
                    "dt": int(rec["dt"]),
                    "ts": rec["ts"],
                    "mm": float(rec.get("mm", 0.0)),
                }])
                rain_count += 1
            except Exception:
                pass

        dec_count = 0
        for rec in state_data.get("decision_log", []):
            try:
                self.append_decision({
                    "ts":               rec["ts"],
                    "suppress":         bool(rec.get("suppress", False)),
                    "reasons":          rec.get("reasons", []),
                    "pop_max":          float(rec.get("pop_max", 0.0)),
                    "forecast_rain_mm": float(rec.get("forecast_rain_mm", 0.0)),
                    "recent_rain_mm":   float(rec.get("recent_rain_mm", 0.0)),
                })
                dec_count += 1
            except Exception:
                pass

        if rain_count or dec_count:
            log.info(
                "Migrated %d rainfall + %d decision records from JSON to SQLite",
                rain_count, dec_count,
            )
