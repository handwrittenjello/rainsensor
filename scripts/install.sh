#!/usr/bin/env bash
# Rain Sensor Bypass Controller — Installation Script
# Run as a normal user (pi); will prompt for sudo where needed.
set -euo pipefail

INSTALL_DIR="/opt/rain-sensor"
LOG_DIR="/var/log/rain-sensor"
STATE_DIR="/var/lib/rain-sensor"

echo "=== Rain Sensor Bypass Controller — Installer ==="
echo ""

# ── System dependencies ───────────────────────────────────────────────────────
echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y python3 python3-venv python3-pip i2c-tools git

# ── Add pi user to i2c/gpio groups ───────────────────────────────────────────
echo "[2/6] Adding $USER to i2c and gpio groups..."
sudo usermod -aG i2c,gpio "$USER"
echo "      NOTE: You must log out and back in (or reboot) for group changes to take effect."

# ── Create directories ────────────────────────────────────────────────────────
echo "[3/6] Creating directories..."
sudo mkdir -p "$INSTALL_DIR" "$LOG_DIR" "$STATE_DIR"
sudo chown "$USER:$USER" "$INSTALL_DIR" "$LOG_DIR" "$STATE_DIR"

# ── Python virtual environment ────────────────────────────────────────────────
echo "[4/6] Setting up Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -e "$INSTALL_DIR"

# ── Config files ──────────────────────────────────────────────────────────────
echo "[5/6] Setting up configuration..."

if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
    cp "$INSTALL_DIR/config.yaml.example" "$INSTALL_DIR/config.yaml"
    echo "      Created config.yaml — edit it now to set your lat/lon and relay settings."
else
    echo "      config.yaml already exists — skipping."
fi

if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    echo "      Created .env — add your OWM_API_KEY before starting the service."
else
    echo "      .env already exists — skipping."
fi

# ── systemd services ──────────────────────────────────────────────────────────
echo "[6/6] Installing systemd services..."
sudo cp "$INSTALL_DIR/systemd/rain-sensor.service"     /etc/systemd/system/
sudo cp "$INSTALL_DIR/systemd/rain-sensor-web.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rain-sensor rain-sensor-web

echo ""
echo "=== Installation complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit $INSTALL_DIR/config.yaml (set lat, lon, relay settings)"
echo "  2. Edit $INSTALL_DIR/.env       (set OWM_API_KEY)"
echo "  3. Enable I2C if not already:   sudo raspi-config → Interface Options → I2C"
echo "  4. Verify relay detected:       sudo i2cdetect -y 1  (look for '10' at 0x10)"
echo "  5. Start services:"
echo "       sudo systemctl start rain-sensor"
echo "       sudo systemctl start rain-sensor-web"
echo "  6. Check status:"
echo "       sudo systemctl status rain-sensor rain-sensor-web"
echo "  7. Open web dashboard: http://$(hostname).local:5000"
echo ""
echo "One-shot test (before starting services):"
echo "  $INSTALL_DIR/venv/bin/python -m rain_sensor force-close  # relay should click"
echo "  $INSTALL_DIR/venv/bin/python -m rain_sensor force-open   # relay clicks again"
echo "  $INSTALL_DIR/venv/bin/python -m rain_sensor clear-override"
echo "  $INSTALL_DIR/venv/bin/python -m rain_sensor check        # full weather check"
