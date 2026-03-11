"""
I2C relay backend for the GeeekPi DockerPi 4-Channel Relay (EP-0099).

Hardware details:
  - Chip: PCF8574 I/O expander
  - Default I2C address: 0x10 (configurable via DIP switches to 0x11–0x13)
  - Control registers: channel 1 = 0x01, ch2 = 0x02, ch3 = 0x03, ch4 = 0x04
  - Write 0xFF to register → relay energized (LED on)
  - Write 0x00 to register → relay de-energized (LED off)
  - Contacts: COM, NO, NC available on each channel screw terminal

Verify your board is detected before running:
  sudo i2cdetect -y 1   # should show "10" at address 0x10

Quick hardware smoke test (no Python needed):
  i2cset -y 1 0x10 0x01 0xFF   # energize channel 1 — relay clicks, LED on
  i2cset -y 1 0x10 0x01 0x00   # de-energize — relay clicks, LED off
"""

from __future__ import annotations
import logging

from rain_sensor.relay.base import RelayBackend

log = logging.getLogger(__name__)

_REG_ON  = 0xFF
_REG_OFF = 0x00

_CHANNEL_REGISTER: dict[int, int] = {
    1: 0x01,
    2: 0x02,
    3: 0x03,
    4: 0x04,
}


class GeeekPiRelayBackend(RelayBackend):
    """
    Controls a single channel on the GeeekPi EP-0099 relay HAT via I2C.
    """

    def __init__(self, address: int = 0x10, channel: int = 1, bus_num: int = 1) -> None:
        if channel not in _CHANNEL_REGISTER:
            raise ValueError(f"Channel must be 1–4, got {channel}")

        self._address  = address
        self._register = _CHANNEL_REGISTER[channel]
        self._channel  = channel

        # Import smbus2 here (not at module level) so other modules can be
        # imported on non-Pi systems (e.g., during unit tests with a mock bus).
        import smbus2
        self._bus = smbus2.SMBus(bus_num)
        self._energized = False

        log.debug(
            "GeeekPiRelayBackend init: I2C addr=0x%02X channel=%d register=0x%02X bus=%d",
            address, channel, self._register, bus_num,
        )

    def energize(self) -> None:
        self._bus.write_byte_data(self._address, self._register, _REG_ON)
        self._energized = True
        log.debug("Relay channel %d ENERGIZED (0x%02X ← 0xFF)", self._channel, self._register)

    def de_energize(self) -> None:
        self._bus.write_byte_data(self._address, self._register, _REG_OFF)
        self._energized = False
        log.debug("Relay channel %d DE-ENERGIZED (0x%02X ← 0x00)", self._channel, self._register)

    def is_energized(self) -> bool:
        return self._energized

    def close(self) -> None:
        """Release the I2C bus. Call on shutdown."""
        try:
            self._bus.close()
        except Exception:
            pass
