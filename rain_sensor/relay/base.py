"""
Abstract relay backend interface.

All relay HAT drivers implement this interface so the rest of the codebase
is completely decoupled from hardware specifics.

Wiring contract for this project:
  - Relay COM → Hunter X Pro SEN terminal ①
  - Relay NC  → Hunter X Pro SEN terminal ②
  - Relay DE-ENERGIZED → NC is CLOSED → circuit closed → Hunter ALLOWS watering
  - Relay ENERGIZED    → NC is OPEN   → circuit open   → Hunter SUPPRESSES watering
"""

from __future__ import annotations
from abc import ABC, abstractmethod


class RelayBackend(ABC):

    @abstractmethod
    def energize(self) -> None:
        """Energize the relay coil (opens NC contact → Hunter stops watering)."""

    @abstractmethod
    def de_energize(self) -> None:
        """De-energize the relay coil (closes NC contact → Hunter runs normally)."""

    @abstractmethod
    def is_energized(self) -> bool:
        """Return True if the relay coil is currently energized."""

    # ── Semantic helpers (preferred call sites) ───────────────────────────────

    def suppress_watering(self) -> None:
        """Open the sensor circuit so the Hunter X Pro suppresses watering."""
        self.energize()

    def allow_watering(self) -> None:
        """Close the sensor circuit so the Hunter X Pro runs normally."""
        self.de_energize()
