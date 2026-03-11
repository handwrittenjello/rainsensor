"""
Relay HAT abstraction factory.

Usage:
    from rain_sensor.relay import get_relay
    relay = get_relay(config.relay)
    relay.suppress_watering()   # energize → NC opens → Hunter stops
    relay.allow_watering()      # de-energize → NC closes → Hunter runs
"""

from rain_sensor.relay.base import RelayBackend
from rain_sensor.config import RelayConfig


def get_relay(config: RelayConfig) -> RelayBackend:
    """Return the correct RelayBackend for the configured driver."""
    if config.driver == "i2c":
        from rain_sensor.relay.i2c_backend import GeeekPiRelayBackend
        return GeeekPiRelayBackend(
            address=config.i2c.address,
            channel=config.channel,
            bus_num=config.i2c.bus,
        )
    elif config.driver == "gpio":
        from rain_sensor.relay.gpio_backend import GpioRelayBackend
        return GpioRelayBackend(
            pin=config.gpio.pin,
            active_low=config.active_low,
        )
    else:
        raise ValueError(
            f"Unknown relay driver: {config.driver!r}. "
            "Expected 'i2c' or 'gpio'."
        )


__all__ = ["get_relay", "RelayBackend"]
