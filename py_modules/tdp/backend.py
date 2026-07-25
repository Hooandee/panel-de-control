from abc import ABC, abstractmethod

from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult


class TDPBackend(ABC):
    supported: bool = True
    supports_levels: bool = False
    blocking: bool = False
    name: str = "base"
    readback: bool = True
    guard_interval_s: float = 2.0
    heartbeat_s: float | None = None
    read_tolerance_w: int = 0
    probe_trace: tuple[dict, ...] = ()

    @abstractmethod
    def get_limits(self) -> TdpLimits:
        """Authoritative limits for this device (read from sysfs when available)."""

    @abstractmethod
    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        """Apply a sustained TDP target in watts. Must never raise. Reads back to verify."""

    @abstractmethod
    def read_applied(self) -> int | None:
        """Currently-applied sustained limit in watts, or None if unreadable."""

    def level_limits(self) -> dict:
        """Per-PL min/max bounds. Returns empty dict on backends without PL support."""
        return {}

    def set_levels(self, pl1: int, pl2: int, pl3: int, ac: bool) -> TdpResult:
        """Set explicit per-PL targets. Defaults to applying pl1 via set_tdp."""
        return self.set_tdp(pl1, ac)

    def observe(self) -> TdpObservation:
        applied = self.read_applied()
        surfaces = {}
        if applied is not None:
            surfaces[self.name] = {"pl1": RailReading(applied)}
        return TdpObservation(readable=self.readback, surfaces=surfaces)

    def reconciliation_levels(self, levels: dict) -> dict[str, int]:
        rails = ("pl1", "pl2", "pl3") if self.supports_levels else ("pl1",)
        return {rail: int(levels[rail]) for rail in rails}

    def profile_choices(self) -> list:
        return []

    def read_profile(self) -> str | None:
        return None

    def set_profile(self, mode: str) -> bool:
        return False


class NullBackend(TDPBackend):
    supported = False
    name = "unsupported"
    readback = False
    guard_interval_s = 0.0

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def get_limits(self) -> TdpLimits:
        return TdpLimits(min_w=0, default_w=0, max_w=0, max_ac_w=0)

    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        return TdpResult(watts, None, False, f"TDP unsupported on this device: {self._reason}")

    def read_applied(self) -> int | None:
        return None
