"""
Command-line entry point.

Usage:
  python -m rain_sensor <subcommand> [options]
  # or, after pip install:
  rain-sensor <subcommand> [options]

Subcommands:
  run            Start the scheduler (blocking — used by systemd).
  check          One-shot weather check + relay update, then exit.
  force-close    Energize relay (suppress watering) + set manual override.
  force-open     De-energize relay (allow watering) + set manual override.
  clear-override Remove manual override, return to automatic control.
  status         Print last decision and relay state from state.json.
  web            Start the Flask web dashboard (blocking).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def _default_config() -> str:
    """Look for config.yaml next to this file, then in cwd."""
    candidates = [
        Path(__file__).parent.parent / "config.yaml",
        Path("config.yaml"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "config.yaml"


def _setup_logging(config) -> None:
    handlers: list[logging.Handler] = []

    log_path = Path(config.paths.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handlers.append(logging.FileHandler(log_path))

    if config.logging.console:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=getattr(logging, config.logging.level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        handlers=handlers,
    )


def _load(args) -> tuple:
    """Load config, state, relay, and cache from parsed args."""
    from rain_sensor.config import load_config
    from rain_sensor.state import StateManager
    from rain_sensor.relay import get_relay
    from rain_sensor.weather.cache import WeatherCache

    cfg   = load_config(args.config)
    state = StateManager(cfg.paths.state_file)
    relay = get_relay(cfg.relay)
    cache = WeatherCache(state, cfg.weather.cache_ttl_minutes)
    return cfg, state, relay, cache


# ── Subcommand handlers ───────────────────────────────────────────────────────

def cmd_run(args) -> None:
    from rain_sensor.scheduler import start_scheduler

    cfg, state, relay, cache = _load(args)
    _setup_logging(cfg)
    log = logging.getLogger(__name__)
    log.info("Rain Sensor Bypass Controller starting (scheduler mode)")
    start_scheduler(cfg, relay, state, cache)


def cmd_check(args) -> None:
    from rain_sensor.scheduler import check_and_set

    cfg, state, relay, cache = _load(args)
    _setup_logging(cfg)
    log = logging.getLogger(__name__)
    log.info("Running one-shot weather check")
    decision = check_and_set(cfg, relay, state, cache)
    if decision:
        print("suppress:", decision.suppress)
        for r in decision.reasons:
            print(" ", r)


def cmd_force_close(args) -> None:
    """Energize relay (open NC contact → Hunter suppresses watering)."""
    cfg, state, relay, _ = _load(args)
    _setup_logging(cfg)
    log = logging.getLogger(__name__)
    log.info("MANUAL OVERRIDE: force-close (suppress watering)")
    relay.suppress_watering()
    state.set_relay_state("suppressed")
    state.set_manual_override("suppress")
    print("Relay energized. NC contact is OPEN. Hunter will suppress watering.")
    print("Run 'clear-override' to return to automatic mode.")


def cmd_force_open(args) -> None:
    """De-energize relay (close NC contact → Hunter runs normally)."""
    cfg, state, relay, _ = _load(args)
    _setup_logging(cfg)
    log = logging.getLogger(__name__)
    log.info("MANUAL OVERRIDE: force-open (allow watering)")
    relay.allow_watering()
    state.set_relay_state("allowed")
    state.set_manual_override("allow")
    print("Relay de-energized. NC contact is CLOSED. Hunter will run normally.")
    print("Run 'clear-override' to return to automatic mode.")


def cmd_clear_override(args) -> None:
    cfg, state, _, _ = _load(args)
    _setup_logging(cfg)
    log = logging.getLogger(__name__)
    state.clear_manual_override()
    log.info("Manual override cleared — returning to automatic control")
    print("Manual override cleared. Automatic weather-based control is now active.")


def cmd_status(args) -> None:
    cfg, state, relay, _ = _load(args)

    data = state.load()
    relay_state   = data.get("relay_state", "unknown")
    override      = data.get("manual_override")
    last_decision = (data.get("decision_log") or [None])[-1]
    cached_age    = state.get_cached_forecast_age_minutes()
    recent_rain   = state.get_recent_rainfall_mm(hours=24)

    print(f"Relay state    : {relay_state}")
    print(f"Manual override: {override or 'none (automatic)'}")
    print(f"Recent rain    : {recent_rain:.1f} mm (past 24 h)")
    if cached_age is not None:
        print(f"Cache age      : {cached_age:.1f} min")
    if last_decision:
        print(f"Last check     : {last_decision['ts']}")
        print(f"  Suppress     : {last_decision['suppress']}")
        for r in last_decision.get("reasons", []):
            print(f"  Reason       : {r}")


def cmd_web(args) -> None:
    cfg, state, relay, cache = _load(args)
    _setup_logging(cfg)
    log = logging.getLogger(__name__)

    host = args.host or cfg.web.host
    port = args.port or cfg.web.port

    log.info("Starting web dashboard on http://%s:%d", host, port)

    from rain_sensor.web.app import create_app
    app = create_app(cfg, state, relay, cache)
    app.run(host=host, port=port, debug=False)


# ── Argument parser ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rain-sensor",
        description="Predictive rain sensor bypass for Hunter X Pro sprinkler systems",
    )
    parser.add_argument(
        "--config", "-c",
        default=_default_config(),
        metavar="PATH",
        help="Path to config.yaml (default: auto-detected)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run",   help="Start scheduler (blocking)")
    sub.add_parser("check", help="One-shot weather check and relay update")
    sub.add_parser("force-close",    help="Energize relay (suppress watering) + set override")
    sub.add_parser("force-open",     help="De-energize relay (allow watering) + set override")
    sub.add_parser("clear-override", help="Remove override, return to automatic")
    sub.add_parser("status",         help="Show current state and last decision")

    web_p = sub.add_parser("web", help="Start the Flask web dashboard (blocking)")
    web_p.add_argument("--host", default=None)
    web_p.add_argument("--port", default=None, type=int)

    args = parser.parse_args()

    dispatch = {
        "run":            cmd_run,
        "check":          cmd_check,
        "force-close":    cmd_force_close,
        "force-open":     cmd_force_open,
        "clear-override": cmd_clear_override,
        "status":         cmd_status,
        "web":            cmd_web,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
