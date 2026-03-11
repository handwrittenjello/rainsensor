"""
Tests for relay backend logic — uses a mock backend so no hardware needed.
Also tests the factory function with a mock i2c module.
"""

import sys
import pytest
from unittest.mock import MagicMock, patch
from rain_sensor.relay.base import RelayBackend


# ── Concrete mock backend ─────────────────────────────────────────────────────

class MockRelayBackend(RelayBackend):
    """In-memory relay backend for testing without hardware."""

    def __init__(self):
        self._energized = False
        self.energize_count = 0
        self.de_energize_count = 0

    def energize(self):
        self._energized = True
        self.energize_count += 1

    def de_energize(self):
        self._energized = False
        self.de_energize_count += 1

    def is_energized(self) -> bool:
        return self._energized


# ── Base class semantic helpers ───────────────────────────────────────────────

def test_suppress_watering_energizes():
    relay = MockRelayBackend()
    relay.suppress_watering()
    assert relay.is_energized() is True
    assert relay.energize_count == 1


def test_allow_watering_de_energizes():
    relay = MockRelayBackend()
    relay.energize()           # start energized
    relay.allow_watering()
    assert relay.is_energized() is False
    assert relay.de_energize_count == 1


def test_initial_state_de_energized():
    relay = MockRelayBackend()
    assert relay.is_energized() is False


def test_toggle_sequence():
    relay = MockRelayBackend()
    relay.suppress_watering()
    relay.allow_watering()
    relay.suppress_watering()
    assert relay.is_energized() is True
    assert relay.energize_count == 2
    assert relay.de_energize_count == 1


# ── GeeekPi I2C backend (mocked smbus2) ──────────────────────────────────────

def _make_i2c_backend(address=0x10, channel=1):
    """
    Instantiate GeeekPiRelayBackend with a mocked smbus2.
    smbus2 is imported lazily inside __init__, so we inject it via sys.modules.
    """
    mock_smbus2 = MagicMock()
    mock_bus = MagicMock()
    mock_smbus2.SMBus.return_value = mock_bus

    with patch.dict(sys.modules, {"smbus2": mock_smbus2}):
        from rain_sensor.relay.i2c_backend import GeeekPiRelayBackend
        backend = GeeekPiRelayBackend(address=address, channel=channel, bus_num=1)

    return backend, mock_bus


def test_geeekpi_energize_writes_ff():
    backend, mock_bus = _make_i2c_backend(address=0x10, channel=1)
    backend.energize()
    mock_bus.write_byte_data.assert_called_with(0x10, 0x01, 0xFF)
    assert backend.is_energized() is True


def test_geeekpi_de_energize_writes_00():
    backend, mock_bus = _make_i2c_backend(address=0x10, channel=1)
    backend.energize()
    backend.de_energize()
    mock_bus.write_byte_data.assert_called_with(0x10, 0x01, 0x00)
    assert backend.is_energized() is False


def test_geeekpi_channel_register_mapping():
    """Each channel maps to the correct I2C register."""
    expected = {1: 0x01, 2: 0x02, 3: 0x03, 4: 0x04}
    for ch, reg in expected.items():
        backend, mock_bus = _make_i2c_backend(channel=ch)
        backend.energize()
        call = mock_bus.write_byte_data.call_args
        assert call[0][1] == reg, f"Channel {ch} should use register 0x{reg:02X}"


def test_geeekpi_invalid_channel_raises():
    mock_smbus2 = MagicMock()
    with patch.dict(sys.modules, {"smbus2": mock_smbus2}):
        from rain_sensor.relay.i2c_backend import GeeekPiRelayBackend
        with pytest.raises(ValueError, match="Channel must be 1"):
            GeeekPiRelayBackend(channel=5)


# ── Factory (relay/__init__.py) ───────────────────────────────────────────────

def test_factory_returns_geeekpi_for_i2c():
    from rain_sensor.config import RelayConfig, I2cConfig
    cfg = RelayConfig(driver="i2c", channel=1, i2c=I2cConfig(address=0x10, bus=1))

    mock_smbus2 = MagicMock()
    with patch.dict(sys.modules, {"smbus2": mock_smbus2}):
        from rain_sensor.relay import get_relay
        from rain_sensor.relay.i2c_backend import GeeekPiRelayBackend
        relay = get_relay(cfg)
        assert isinstance(relay, GeeekPiRelayBackend)


def test_factory_raises_for_unknown_driver():
    from rain_sensor.config import RelayConfig
    cfg = RelayConfig(driver="zigbee", channel=1)

    from rain_sensor.relay import get_relay
    with pytest.raises(ValueError, match="Unknown relay driver"):
        get_relay(cfg)
