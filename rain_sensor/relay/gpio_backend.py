"""
GPIO relay backend for boards like Waveshare RPi Relay Board and SainSmart.

These boards use a direct GPIO pin per relay channel. Most are active-LOW,
meaning GPIO LOW = relay energized. Set active_low=False in config for the
rare active-HIGH variant.

Waveshare RPi Relay Board (3-channel) default BCM pins:
  Channel 1 = BCM 26
  Channel 2 = BCM 20
  Channel 3 = BCM 21

This backend is NOT used for the GeeekPi EP-0099 (which is I2C).
It is included so the strategy pattern supports common GPIO boards
without any code changes to the rest of the application.
"""

from __future__ import annotations
import logging

from rain_sensor.relay.base import RelayBackend

log = logging.getLogger(__name__)


class GpioRelayBackend(RelayBackend):
    """
    Controls a relay via a single BCM GPIO pin.
    Supports active-LOW (default) and active-HIGH boards.
    """

    def __init__(self, pin: int, active_low: bool = True) -> None:
        # Import RPi.GPIO here so non-Pi environments (tests, dev machines)
        # can import the package without RPi.GPIO installed.
        import RPi.GPIO as GPIO   # type: ignore[import]

        self._GPIO = GPIO
        self._pin = pin
        self._active_low = active_low
        self._energized = False

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(pin, GPIO.OUT)
        # Start de-energized (NC closed = Hunter runs normally)
        self.de_energize()
        log.debug("GpioRelayBackend init: BCM pin=%d active_low=%s", pin, active_low)

    def _write(self, energize: bool) -> None:
        if self._active_low:
            level = self._GPIO.LOW if energize else self._GPIO.HIGH
        else:
            level = self._GPIO.HIGH if energize else self._GPIO.LOW
        self._GPIO.output(self._pin, level)
        self._energized = energize

    def energize(self) -> None:
        self._write(True)
        log.debug("GPIO relay pin %d ENERGIZED", self._pin)

    def de_energize(self) -> None:
        self._write(False)
        log.debug("GPIO relay pin %d DE-ENERGIZED", self._pin)

    def is_energized(self) -> bool:
        return self._energized

    def cleanup(self) -> None:
        """Release GPIO resources. Call on shutdown."""
        try:
            self._GPIO.cleanup(self._pin)
        except Exception:
            pass
