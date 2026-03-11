# Rain Sensor Bypass Controller

A Raspberry Pi–based smart rain sensor bypass for **Hunter X Pro** (and similar) sprinkler
systems. Instead of reacting to rain *while it's falling*, this controller checks
**OpenWeatherMap forecasts** and opens the sprinkler's sensor circuit *before* a scheduled
watering run — preventing waste when rain is already on its way.

A built-in web dashboard shows current status, a 30-day suppression history chart, and a
live precipitation radar map centered on your location.

---

## How It Works

The Hunter X Pro has two **SEN** terminals normally bridged by a factory jumper plate.
Removing that jumper and substituting a relay contact in its place replicates exactly
what a commercial rain sensor does:

| Circuit state | Hunter behaviour |
|---|---|
| Terminals shorted (closed) | Watering runs normally |
| Terminals open (open circuit) | Watering suppressed |

This controller wires the relay's **NC (Normally Closed)** contact across those terminals:

- **Relay de-energized** (default / Pi off): NC is closed → Hunter runs on schedule
- **Relay energized** (rain forecast): NC opens → Hunter suppresses watering

The fail-safe is deliberate: if the Pi loses power, the relay de-energizes and the lawn
continues to water on schedule. A Pi failure causes waste, not drought.

---

## Hardware Requirements

| Component | Details |
|---|---|
| Raspberry Pi | Any model with I2C support (Pi 3/4/5, Pi Zero 2 W tested) |
| **GeeekPi DockerPi 4-Channel Relay (EP-0099)** | [Amazon B07Q2P9D7K](https://www.amazon.com/dp/B07Q2P9D7K) |
| Hunter X Pro controller | Any firmware revision |
| Two short wires | 18–22 AWG, any colour |

No additional hardware is required. The relay HAT already installed on the Pi is all you need.

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

> **Important:** Use the **NC** (Normally Closed) terminal, not NO (Normally Open).
> The NO terminal will produce the opposite logic.

> **Safety:** Both SEN terminals are a dry contact with no dangerous voltage.
> Do **not** wire the relay to any 24 VAC zone terminal — only the SEN posts.

> **Why not a bare GPIO pin?** The Hunter may put up to 24 VAC across the SEN
> terminals to detect continuity. A GPIO pin is rated for 3.3 V / 16 mA — direct
> connection would instantly destroy the Pi. The relay's galvanically isolated contacts
> protect it completely.

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
# Energize Channel 1 — relay clicks, LED turns on, NC contact opens
i2cset -y 1 0x10 0x01 0xFF

# De-energize — relay clicks, LED off, NC contact closes
i2cset -y 1 0x10 0x01 0x00
```

Watch the Hunter X Pro display — when the relay is energized (NC open), the controller
should show a rain-sensor indicator or simply prevent zone activation.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USER/rain-sensor.git /opt/rain-sensor
cd /opt/rain-sensor
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### 3. Configure

```bash
cp config.yaml.example config.yaml
nano config.yaml          # set your lat/lon and review thresholds
```

```bash
cp .env.example .env
nano .env                 # paste your OpenWeatherMap API key
chmod 600 .env            # protect the secret
```

Get a free API key at [openweathermap.org](https://openweathermap.org/api).
The **One Call API 3.0** free tier allows 1,000 calls/day — this controller uses at most
~5/day under default settings.

---

## Configuration Reference

All settings live in `config.yaml`. Secrets (API key) go in `.env`.

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
  forecast_rain_mm:       2.5  # suppress if forecast total >= 2.5 mm
  recent_rain_mm:         5.0  # suppress if past-24h total >= 5.0 mm

schedule:
  times: ["05:30", "22:00"]    # run checks at these times (HH:MM, 24-hour)
  run_on_start: true           # also run immediately when the service starts

weather:
  cache_ttl_minutes: 30        # reuse API response for 30 minutes

paths:
  log_file:   /var/log/rain-sensor/rain_sensor.log
  state_file: /var/lib/rain-sensor/state.json

logging:
  level: INFO      # DEBUG | INFO | WARNING | ERROR
  console: true

web:
  host: 0.0.0.0   # listen on all interfaces
  port: 5000
```

### Threshold tuning guide

| Your goal | Recommended change |
|---|---|
| More aggressive suppression | Lower `rain_probability_pct` (e.g., 30%) |
| Less suppression on light drizzle | Raise `forecast_rain_mm` (e.g., 5.0 mm) |
| Prevent watering after heavy rain | Raise `recent_rain_mm` (e.g., 10.0 mm) |
| Earlier pre-suppression | Add an earlier time to `schedule.times` |

---

## CLI Reference

```bash
# Start the scheduler (blocking — used by systemd)
python -m rain_sensor run

# One-shot weather check + relay update, then exit
python -m rain_sensor check

# Manually energize relay (suppress watering) and lock it
python -m rain_sensor force-close

# Manually de-energize relay (allow watering) and lock it
python -m rain_sensor force-open

# Remove the manual lock, return to automatic
python -m rain_sensor clear-override

# Show current state, last decision, and recent rainfall
python -m rain_sensor status

# Start the web dashboard (blocking)
python -m rain_sensor web --port 5000
```

All commands accept `--config PATH` to point at a non-default config file.

---

## Web Dashboard

Once the web service is running, open a browser on any device on your local network:

```
http://raspberrypi.local:5000
```

(Replace `raspberrypi` with your Pi's hostname, or use its IP address.)

The dashboard shows:

- **Current Status** — relay state, manual override, recent rainfall, last check time
- **Next 6-Hour Forecast** — hourly precipitation probability bars and rain amounts
- **Manual Controls** — Force Suppress / Force Allow / Clear Override buttons
- **30-Day History** — stacked bar chart showing suppressed vs. allowed watering days
- **Radar Map** — live OpenWeatherMap precipitation overlay on a Leaflet.js map

The status panel auto-refreshes every 60 seconds via HTMX without a full page reload.

---

## Running as a Service

### Scheduler service

```bash
sudo cp /opt/rain-sensor/systemd/rain-sensor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rain-sensor
sudo systemctl start rain-sensor
sudo systemctl status rain-sensor
```

### Web dashboard service

```bash
sudo cp /opt/rain-sensor/systemd/rain-sensor-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rain-sensor-web
sudo systemctl start rain-sensor-web
sudo systemctl status rain-sensor-web
```

### View live logs

```bash
journalctl -u rain-sensor -f
journalctl -u rain-sensor-web -f
# or
tail -f /var/log/rain-sensor/rain_sensor.log
```

---

## Suppression Logic

Watering is suppressed if **any one** of three independent conditions is met:

1. **Recent rain** — accumulated `rain.1h` from the past 24 hours ≥ `recent_rain_mm`
   *Example: 6 mm of rain yesterday → skip today's watering*

2. **Forecast rain volume** — sum of `rain.1h` across the next `rain_probability_hours`
   hourly entries ≥ `forecast_rain_mm`
   *Example: 3 mm forecast in the next 3 hours → suppress*

3. **Rain probability** — max `pop` (0–1) across the look-ahead window ≥
   `rain_probability_pct / 100`
   *Example: 70% chance of rain in the next 3 hours → suppress*

All three data points come from the OWM **One Call API 3.0** `hourly[]` array.
The full decision and all matching reasons are written to the log and to `state.json`
for the dashboard.

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
# log out and back in, or:
newgrp i2c
```

### OWM API key errors

```bash
python -m rain_sensor check   # watch for CRITICAL log lines
```

- HTTP 401: key invalid or not yet activated (new keys take up to 2 hours)
- HTTP 429: rate limit hit — reduce `cache_ttl_minutes` or check for multiple instances

### `i2cdetect` shows no devices

- Confirm `dtparam=i2c_arm=on` is in `/boot/config.txt` (raspi-config does this)
- Try `sudo i2cdetect -y 0` (older Pi models use bus 0)
- Check HAT is firmly seated on the 40-pin header

### Service fails to start: "config.yaml not found"

The service unit points at `/opt/rain-sensor/config.yaml`. Either:
- Copy your config there: `cp /path/to/config.yaml /opt/rain-sensor/`
- Or edit the `ExecStart` line in the service file to point at your actual path

### Dashboard shows "Loading…" forever

The Flask web service may not be running:
```bash
sudo systemctl status rain-sensor-web
journalctl -u rain-sensor-web -n 50
```

---

## Community References

Similar projects worth exploring:

- **[ahplummer/pirain](https://github.com/ahplummer/pirain)** — direct rain bypass for
  Hunter/Rainbird systems, minimal approach
- **[miarond/RPi_Irrigation_Bypass_Sensor](https://github.com/miarond/RPi_Irrigation_Bypass_Sensor)** — Flask + CRON relay bypass
- **[Dan-in-CA/SIP](https://github.com/Dan-in-CA/SIP)** — full irrigation control suite for Pi
- **[jeroenterheerdt/HAsmartirrigation](https://github.com/jeroenterheerdt/HAsmartirrigation)** — Home Assistant evapotranspiration-based irrigation

---

## Safety Notes

1. **Only connect to the SEN terminals.** Never connect the relay to a zone terminal or
   the 24 VAC common — this would short out your transformer and damage the controller.

2. **Remove the factory SEN jumper** before wiring. Leaving it in place will always hold
   the circuit closed (watering always allowed) regardless of relay state.

3. **Do not use a bare GPIO pin** in place of the relay. The Hunter may put up to 24 VAC
   across the SEN terminals. GPIO pins are 3.3 V / 16 mA — a direct connection destroys them.

4. **The relay contacts (3 A rated) are far over-spec** for this dry-contact application.
   There is no arc, contact wear, or voltage concern at 0 V.

5. **Run as the `pi` user** (not root). The `i2c` group grants the necessary I2C bus access
   without elevated privileges.

---

## License

MIT — do whatever you like with this. If it saves your lawn (or your water bill), great.
