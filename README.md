# Rain Sensor Bypass Controller

A Raspberry Pi–based smart rain sensor bypass for **Hunter X Pro** (and similar) sprinkler
systems. Instead of reacting to rain *while it's falling*, this controller checks
**OpenWeatherMap forecasts** and closes the sprinkler's sensor circuit *before* a scheduled
watering run — preventing waste when rain is already on its way.

A built-in web dashboard shows current status, a 30-day suppression history chart, a live
precipitation radar map, and historical rainfall data stored in a local SQLite database.

---

## How It Works

The Hunter X Pro has two **SEN** terminals normally bridged by a factory jumper plate.
Removing that jumper and wiring a relay contact in its place replicates exactly what a
commercial rain sensor does:

| SEN terminal circuit | Hunter behaviour |
|---|---|
| Terminals shorted (closed) | Watering **suppressed** (mimics wet rain sensor) |
| Terminals open | Watering **allowed** (mimics dry/absent sensor) |

> **Important:** The Hunter X Pro holds ~24 V DC across the SEN terminals to detect the
> sensor state. A shorted circuit signals "sensor is wet → suppress watering." An open
> circuit signals "dry/no sensor → run normally."

This controller wires the relay's **NC (Normally Closed)** contact across those terminals:

| Relay state | NC contact | SEN circuit | Hunter behaviour |
|---|---|---|---|
| **De-energized** (default) | Closed | Shorted | Watering **suppressed** |
| **Energized** | Open | Open | Watering **allowed** |

**Fail-safe:** If the Pi loses power, the relay de-energizes and the NC contact closes,
suppressing watering. This conserves water rather than risking an unscheduled run.

---

## Hardware Requirements

| Component | Details |
|---|---|
| Raspberry Pi | Any model with I2C support (Pi 3/4/5, Pi Zero 2 W tested) |
| **GeeekPi DockerPi 4-Channel Relay (EP-0099)** | [Amazon B07Q2P9D7K](https://www.amazon.com/dp/B07Q2P9D7K) |
| Hunter X Pro controller | Any firmware revision |
| Two short wires | 18–22 AWG, any colour |

---

## Wiring Guide

### Step 1 — Remove the factory jumper

Open the Hunter X Pro's front cover. Locate the **SEN** terminal strip (usually top-right).
There is a small metal jumper plate bridging two SEN posts. Pull it out and set it aside.

### Step 2 — Wire the relay

Connect two short wires from the **relay HAT screw terminals** (Channel 1) to the
**Hunter X Pro SEN terminals**:

```
GeeekPi EP-0099 Relay HAT          Hunter X Pro Controller
──────────────────────────          ────────────────────────
  Channel 1  COM ──── wire ──────── SEN terminal ①
  Channel 1  NC  ──── wire ──────── SEN terminal ②
```

> **Use the NC terminal** (Normally Closed), not NO (Normally Open).

> **Safety:** The SEN terminals carry ~24 V DC for sensor detection — safe for relay
> contacts but **do not wire to a bare GPIO pin**, which is rated for 3.3 V / 16 mA.
> The relay's galvanically isolated contacts protect the Pi completely.

> **Never** connect the relay to a 24 VAC zone terminal or the common bus.

### Step 3 — Verify wiring

With the Pi **off** (relay de-energized → NC closed → SEN shorted), the Hunter X Pro
should show a rain-sensor suppression indicator. Power the Pi on and the relay will
energize (NC opens, SEN open) and watering should be allowed.

---

## Relay HAT Setup

### Enable I2C on the Raspberry Pi

```bash
sudo raspi-config
# Interface Options → I2C → Enable → Finish
sudo reboot
```

### Verify the board is detected

```bash
sudo apt install -y i2c-tools
sudo i2cdetect -y 1
```

Expected output — you should see **`10`** at address 0x10:

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:          -- -- -- -- -- -- -- -- -- -- -- -- --
10: 10 -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
```

If nothing appears, check that the HAT is firmly seated and I2C is enabled.

### Smoke-test the relay (no Python needed)

```bash
# Energize Channel 1 — relay clicks, LED on, NC opens → SEN open → watering allowed
i2cset -y 1 0x10 0x01 0xFF

# De-energize — relay clicks, LED off, NC closes → SEN shorted → watering suppressed
i2cset -y 1 0x10 0x01 0x00
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USER/rain-sensor.git /home/pi/rainsensor
cd /home/pi/rainsensor
```

### 2. Install dependencies (no virtual environment)

```bash
pip3 install --user --ignore-requires-python -e .
```

> `--ignore-requires-python` is needed if you're on Python 3.9 (Raspbian Bullseye).
> The code is fully compatible with 3.9 despite the pyproject.toml specifying >=3.10.

### 3. Create runtime directories

```bash
sudo mkdir -p /var/lib/rain-sensor /var/log/rain-sensor
sudo chown pi:pi /var/lib/rain-sensor /var/log/rain-sensor
```

### 4. Configure

```bash
cp config.yaml.example config.yaml
nano config.yaml          # set your lat/lon and review thresholds
```

```bash
cp .env.example .env
nano .env                 # paste your OpenWeatherMap One Call API 3.0 key
chmod 600 .env
```

Get a free API key at [openweathermap.org](https://openweathermap.org/api).
The One Call API 3.0 free tier allows 1,000 calls/day — this controller uses at most ~5/day
under default settings.

---

## Configuration Reference

All settings live in `config.yaml`. Secrets (API key) go in `.env`.

Both files are excluded from git via `.gitignore`. All runtime data (SQLite database,
state file, logs) is stored under `/var/lib/rain-sensor/` and `/var/log/rain-sensor/`,
which are also outside the project directory.

```yaml
location:
  lat: 37.7749     # your latitude (decimal degrees)
  lon: -122.4194   # your longitude (negative = west)

relay:
  driver: i2c      # "i2c" for GeeekPi EP-0099
  channel: 1       # relay channel (1–4)
  i2c:
    address: 0x10  # GeeekPi default; run i2cdetect to confirm
    bus: 1

thresholds:
  rain_probability_pct:   50   # suppress if PoP >= 50% in look-ahead window
  rain_probability_hours:  3   # hours ahead to check PoP and rain volume
  forecast_rain_mm:       2.5  # suppress if forecast total >= 2.5 mm (~0.10 in)
  recent_rain_mm:         5.0  # suppress if past-24h total >= 5.0 mm (~0.20 in)

schedule:
  times: ["05:30", "22:00"]    # run checks at these times (HH:MM, 24-hour)
  run_on_start: true           # also run immediately when the service starts

weather:
  cache_ttl_minutes: 30        # reuse API response for 30 minutes

paths:
  log_file:   /var/log/rain-sensor/rain_sensor.log
  state_file: /var/lib/rain-sensor/state.json
  db_file:    /var/lib/rain-sensor/rain_sensor.db   # SQLite historical database

logging:
  level: INFO      # DEBUG | INFO | WARNING | ERROR
  console: true

web:
  host: 0.0.0.0   # listen on all interfaces
  port: 5000
```

### Threshold tuning guide

| Goal | Recommended change |
|---|---|
| More aggressive suppression | Lower `rain_probability_pct` (e.g., 30%) |
| Less suppression on light drizzle | Raise `forecast_rain_mm` (e.g., 5.0 mm) |
| Prevent watering after heavy rain | Raise `recent_rain_mm` (e.g., 10.0 mm) |
| Earlier pre-suppression | Add an earlier time to `schedule.times` |

---

## Running as a Service (pm2)

This project uses **pm2** for process management rather than systemd.

### Install pm2

```bash
sudo npm install -g pm2
```

### Start both services

```bash
cd /home/pi/rainsensor
pm2 start ecosystem.config.js
```

### Enable auto-start on boot

```bash
pm2 save
pm2 startup   # this prints a command — copy and run it with sudo
# Example output:
# sudo env PATH=$PATH:/usr/bin /usr/local/lib/node_modules/pm2/bin/pm2 startup systemd -u pi --hp /home/pi
pm2 save --force   # save the process list after running the above
```

### Common pm2 commands

```bash
pm2 list                        # show process status
pm2 logs rain-sensor            # tail scheduler logs
pm2 logs rain-sensor-web        # tail web dashboard logs
pm2 restart all                 # restart both services
pm2 restart rain-sensor         # restart scheduler only
pm2 delete all && pm2 start ecosystem.config.js   # full reset
```

---

## CLI Reference

> **Note:** `--config PATH` must come **before** the subcommand.

```bash
# Start the scheduler (blocking — used by pm2)
python3 -m rain_sensor --config config.yaml run

# Start the web dashboard (blocking — used by pm2)
python3 -m rain_sensor --config config.yaml web

# One-shot weather check + relay update, then exit
python3 -m rain_sensor --config config.yaml check

# Manually suppress watering (locks relay, ignores schedule)
python3 -m rain_sensor --config config.yaml force-close

# Manually allow watering (locks relay, ignores schedule)
python3 -m rain_sensor --config config.yaml force-open

# Remove the manual lock, return to automatic
python3 -m rain_sensor --config config.yaml clear-override

# Show current state, last decision, and recent rainfall
python3 -m rain_sensor --config config.yaml status
```

---

## Web Dashboard

Once the web service is running, open a browser on any device on your local network:

```
http://raspberrypi.local:5000
```

(Replace `raspberrypi.local` with your Pi's hostname or IP address.)

The dashboard shows:

- **Current Status** — relay state, manual override indicator, recent rainfall (inches),
  last check time, and last decision reasons
- **Override Banner** — prominent yellow/orange alert when a manual override is active
- **Next 6-Hour Forecast** — hourly precipitation probability and rain amounts in inches,
  temperature in °F
- **Manual Controls**
  - **Force Suppress** — lock the relay to suppress watering regardless of forecast
  - **Force Allow** — lock the relay to allow watering regardless of forecast
  - **Clear Override** — return to automatic mode and immediately re-evaluate the forecast
  - **Check Now** — force an immediate weather check outside the normal schedule
- **30-Day History** — stacked bar chart (suppressed vs. allowed days) from SQLite
- **Radar Map** — live RainViewer precipitation radar iframe, centered on your location,
  zoomed to show your region

The status panel auto-refreshes every 60 seconds via HTMX without a full page reload.
All rain amounts display in **imperial units** (inches, °F).

---

## External Status API

A JSON API is available for integration with home dashboards (Home Assistant, MagicMirror,
Grafana, custom scripts, etc.):

```
GET http://raspberrypi.local:5000/api/v1/status
```

Example response:

```json
{
  "relay_state": "allowed",
  "suppress": false,
  "override": null,
  "override_active": false,
  "recent_rain_in": 0.12,
  "rainfall_24h_in": 0.12,
  "rainfall_7d_in": 0.55,
  "cache_age_min": 14.3,
  "last_check": {
    "ts": "2025-06-01T05:30:00+00:00",
    "suppress": false,
    "reasons": ["No significant rain forecast in next 3 h"],
    "pop_max_pct": 10,
    "forecast_rain_in": 0.0
  },
  "forecast": [
    { "dt": 1748750400, "time": "05:00", "pop_pct": 10, "rain_in": 0.0, "temp_f": 74.1 }
  ],
  "thresholds": {
    "rain_probability_pct": 50,
    "rain_probability_hours": 3,
    "forecast_rain_in": 0.10,
    "recent_rain_in": 0.20
  }
}
```

---

## Data Storage

All runtime data is stored **outside the project directory** and will never be committed
to git:

| Path | Contents |
|---|---|
| `/var/lib/rain-sensor/rain_sensor.db` | SQLite database — full rainfall history and decision log |
| `/var/lib/rain-sensor/state.json` | Current relay state, manual override, cached forecast |
| `/var/log/rain-sensor/rain_sensor.log` | Application log |

The SQLite database stores every hourly rainfall reading from OWM and a full log of every
suppression decision, enabling historical queries and long-term trend analysis.

---

## Suppression Logic

Watering is suppressed if **any one** of three independent conditions is met:

1. **Recent rain** — accumulated `rain.1h` from the past 24 hours ≥ `recent_rain_mm`
   *Example: 6 mm (0.24 in) of rain yesterday → skip today's watering*

2. **Forecast rain volume** — sum of `rain.1h` across the next `rain_probability_hours`
   hourly entries ≥ `forecast_rain_mm`
   *Example: 3 mm (0.12 in) forecast in the next 3 hours → suppress*

3. **Rain probability** — max `pop` (0–1) across the look-ahead window ≥
   `rain_probability_pct / 100`
   *Example: 70% chance of rain in the next 3 hours → suppress*

All three data points come from the OWM **One Call API 3.0** `hourly[]` array using
`units=imperial`. The full decision and all matching reasons are written to the log and
to the SQLite database for the dashboard history chart.

---

## Troubleshooting

### Relay not clicking on `force-close`

```bash
sudo i2cdetect -y 1   # confirm address 0x10 is visible
```

If 0x10 is absent: check the HAT is seated, I2C is enabled in `raspi-config`,
and the user running the script is in the `i2c` group:

```bash
sudo usermod -aG i2c pi
newgrp i2c
```

### Hunter X Pro not responding to relay

Verify polarity with a multimeter across the SEN terminals:
- **Relay de-energized** (NC closed): multimeter should read ~0 Ω (shorted) → Hunter suppresses
- **Relay energized** (NC open): multimeter should read open → Hunter allows watering

The Hunter holds ~24 V DC across the SEN terminals. Confirm by measuring voltage
with nothing connected — you should read ~24 V DC.

### OWM API key errors

```bash
pm2 logs rain-sensor   # watch for CRITICAL or ERROR lines
```

- HTTP 401: key invalid or not yet activated (new keys take up to 2 hours)
- HTTP 429: rate limit hit — reduce `cache_ttl_minutes` or check for multiple instances

### pm2 processes not starting after reboot

Re-run the full startup sequence:
```bash
pm2 delete all
pm2 start ecosystem.config.js
pm2 save --force
sudo env PATH=$PATH:/usr/bin /usr/local/lib/node_modules/pm2/bin/pm2 startup systemd -u pi --hp /home/pi
pm2 save --force
```

### Dashboard shows "Loading…" forever

```bash
pm2 logs rain-sensor-web   # check for startup errors
pm2 list                   # confirm rain-sensor-web is "online"
```

### `ModuleNotFoundError: No module named 'rain_sensor'`

The `PYTHONPATH` in `ecosystem.config.js` must point to `/home/pi/rainsensor`. Verify:

```bash
cat ecosystem.config.js   # env.PYTHONPATH should be /home/pi/rainsensor
```

---

## API Testing (Bruno)

A [Bruno](https://www.usebruno.com/) test collection is included at `tests/bruno/`.

Import the collection into the Bruno desktop app, select the **Local** environment
(pre-configured to `http://raspberrypi.local:5000`), and run all requests.

The suite covers all endpoints: status, forecast, history, external API, force check,
and all three override modes.

---

## Community References

- **[ahplummer/pirain](https://github.com/ahplummer/pirain)** — direct rain bypass for Hunter/Rainbird, minimal approach
- **[miarond/RPi_Irrigation_Bypass_Sensor](https://github.com/miarond/RPi_Irrigation_Bypass_Sensor)** — Flask + CRON relay bypass
- **[Dan-in-CA/SIP](https://github.com/Dan-in-CA/SIP)** — full irrigation control suite for Pi
- **[jeroenterheerdt/HAsmartirrigation](https://github.com/jeroenterheerdt/HAsmartirrigation)** — Home Assistant evapotranspiration-based irrigation

---

## Safety Notes

1. **Only connect to the SEN terminals.** Never connect the relay to a zone terminal or
   the 24 VAC common — this would short your transformer and damage the controller.

2. **Remove the factory SEN jumper** before wiring. Leaving it in place will always hold
   the circuit closed regardless of relay state.

3. **Do not use a bare GPIO pin** in place of the relay. The Hunter holds ~24 V DC across
   the SEN terminals. GPIO pins are rated 3.3 V / 16 mA — a direct connection destroys them.

4. **Run as the `pi` user** (not root). The `i2c` group grants the necessary I2C bus access
   without elevated privileges.

---

## License

MIT — do whatever you like with this. If it saves your lawn (or your water bill), great.
