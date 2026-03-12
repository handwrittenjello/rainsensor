"""
Configuration loader.

Reads config.yaml for all settings, then overlays secrets from the .env file
(or the real environment). Exposes a single frozen Config dataclass so every
other module has one import to get all values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ThresholdConfig:
    rain_probability_pct: int    = 50    # suppress if max hourly PoP >= this %
    rain_probability_hours: int  = 3     # hours ahead to inspect
    forecast_rain_mm: float      = 2.5   # suppress if forecast total >= this mm
    recent_rain_mm: float        = 5.0   # suppress if past-24h total >= this mm


@dataclass(frozen=True)
class I2cConfig:
    address: int = 0x10   # GeeekPi EP-0099 default
    bus: int     = 1


@dataclass(frozen=True)
class GpioConfig:
    pin: int      = 26    # BCM pin (Waveshare channel 1 default)


@dataclass(frozen=True)
class RelayConfig:
    driver:     str              = "i2c"   # "i2c" | "gpio"
    channel:    int              = 1
    active_low: bool             = True    # GPIO driver only
    i2c:        I2cConfig        = field(default_factory=I2cConfig)
    gpio:       GpioConfig       = field(default_factory=GpioConfig)


@dataclass(frozen=True)
class ScheduleConfig:
    times:         list[str] = field(default_factory=lambda: ["05:30", "22:00"])
    run_on_start:  bool      = True


@dataclass(frozen=True)
class WeatherConfig:
    cache_ttl_minutes: int = 30


@dataclass(frozen=True)
class PathsConfig:
    log_file:   str = "/var/log/rain-sensor/rain_sensor.log"
    state_file: str = "/var/lib/rain-sensor/state.json"
    db_file:    str = "/var/lib/rain-sensor/rain_sensor.db"


@dataclass(frozen=True)
class LoggingConfig:
    level:   str  = "INFO"
    console: bool = True


@dataclass(frozen=True)
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 5000


@dataclass(frozen=True)
class Config:
    lat:        float
    lon:        float
    owm_api_key: str
    relay:      RelayConfig
    thresholds: ThresholdConfig
    schedule:   ScheduleConfig
    weather:    WeatherConfig
    paths:      PathsConfig
    logging:    LoggingConfig
    web:        WebConfig


# ── Loader ────────────────────────────────────────────────────────────────────

def load_config(yaml_path: str, env_path: Optional[str] = None) -> Config:
    """
    Load configuration from *yaml_path*, injecting secrets from *env_path*
    (defaults to a .env file next to the YAML if it exists).
    """
    yaml_file = Path(yaml_path)
    if not yaml_file.exists():
        raise FileNotFoundError(f"Config file not found: {yaml_path}")

    # Load .env (silently ignored if absent — real env vars take precedence)
    if env_path:
        load_dotenv(env_path, override=False)
    else:
        load_dotenv(yaml_file.parent / ".env", override=False)

    with yaml_file.open() as f:
        raw = yaml.safe_load(f) or {}

    owm_api_key = os.environ.get("OWM_API_KEY", "")
    if not owm_api_key:
        raise ValueError(
            "OWM_API_KEY is not set. Add it to your .env file or environment."
        )

    loc = raw.get("location", {})
    relay_raw = raw.get("relay", {})
    thr = raw.get("thresholds", {})
    sched = raw.get("schedule", {})
    weather_raw = raw.get("weather", {})
    paths_raw = raw.get("paths", {})
    log_raw = raw.get("logging", {})
    web_raw = raw.get("web", {})

    i2c_raw = relay_raw.get("i2c", {})
    gpio_raw = relay_raw.get("gpio", {})

    return Config(
        lat=float(loc.get("lat", 0.0)),
        lon=float(loc.get("lon", 0.0)),
        owm_api_key=owm_api_key,
        relay=RelayConfig(
            driver=relay_raw.get("driver", "i2c"),
            channel=int(relay_raw.get("channel", 1)),
            active_low=bool(relay_raw.get("active_low", True)),
            i2c=I2cConfig(
                address=int(str(i2c_raw.get("address", "0x10")), 16)
                        if isinstance(i2c_raw.get("address"), str)
                        else int(i2c_raw.get("address", 0x10)),
                bus=int(i2c_raw.get("bus", 1)),
            ),
            gpio=GpioConfig(
                pin=int(gpio_raw.get("pin", 26)),
            ),
        ),
        thresholds=ThresholdConfig(
            rain_probability_pct=int(thr.get("rain_probability_pct", 50)),
            rain_probability_hours=int(thr.get("rain_probability_hours", 3)),
            forecast_rain_mm=float(thr.get("forecast_rain_mm", 2.5)),
            recent_rain_mm=float(thr.get("recent_rain_mm", 5.0)),
        ),
        schedule=ScheduleConfig(
            times=sched.get("times", ["05:30", "22:00"]),
            run_on_start=bool(sched.get("run_on_start", True)),
        ),
        weather=WeatherConfig(
            cache_ttl_minutes=int(weather_raw.get("cache_ttl_minutes", 30)),
        ),
        paths=PathsConfig(
            log_file=paths_raw.get("log_file", "/var/log/rain-sensor/rain_sensor.log"),
            state_file=paths_raw.get("state_file", "/var/lib/rain-sensor/state.json"),
            db_file=paths_raw.get("db_file", "/var/lib/rain-sensor/rain_sensor.db"),
        ),
        logging=LoggingConfig(
            level=log_raw.get("level", "INFO").upper(),
            console=bool(log_raw.get("console", True)),
        ),
        web=WebConfig(
            host=web_raw.get("host", "0.0.0.0"),
            port=int(web_raw.get("port", 5000)),
        ),
    )
