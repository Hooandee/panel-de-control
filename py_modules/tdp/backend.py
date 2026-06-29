from abc import ABC, abstractmethod

from tdp.types import TdpLimits, TdpResult


class TDPBackend(ABC):
    supported: bool = True
    name: str = "base"

    @abstractmethod
    def get_limits(self) -> TdpLimits:
        """Authoritative limits for this device (read from sysfs when available)."""

    @abstractmethod
    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        """Apply a sustained TDP target in watts. Must never raise. Reads back to verify."""

    @abstractmethod
    def read_applied(self) -> int | None:
        """Currently-applied sustained limit in watts, or None if unreadable."""


class NullBackend(TDPBackend):
    supported = False
    name = "unsupported"

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def get_limits(self) -> TdpLimits:
        return TdpLimits(min_w=0, default_w=0, max_w=0, max_ac_w=0)

    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        return TdpResult(watts, None, False, f"TDP unsupported on this device: {self._reason}")

    def read_applied(self) -> int | None:
        return None
