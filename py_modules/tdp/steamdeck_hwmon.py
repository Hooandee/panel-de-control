import glob
import os

from tdp.backend import TDPBackend
from tdp.types import TdpLimits, TdpResult

_HWMON = "sys/class/hwmon"
_PREFERRED_NAMES = ("steamdeck_hwmon", "amdgpu", "jupiter")


class SteamDeckHwmonBackend(TDPBackend):
    """Steam Deck TDP via hwmon power cap (microwatts). Never raises."""

    name = "steamdeck-hwmon"

    def __init__(self, fallback: TdpLimits, root: str = "/") -> None:
        self._fallback = fallback
        self._root = root
        self._cap = self._find_cap()
        self.supported = self._cap is not None

    def _hwmon_name(self, d: str) -> str:
        try:
            with open(os.path.join(d, "name")) as f:
                return f.read().strip()
        except OSError:
            return ""

    def _find_cap(self) -> str | None:
        dirs = sorted(glob.glob(os.path.join(self._root, _HWMON, "hwmon*")))
        # preferred names first, then any hwmon exposing a power*_cap
        ordered = sorted(
            dirs,
            key=lambda d: (
                _PREFERRED_NAMES.index(n)
                if (n := self._hwmon_name(d)) in _PREFERRED_NAMES
                else len(_PREFERRED_NAMES)
            ),
        )
        for d in ordered:
            caps = sorted(glob.glob(os.path.join(d, "power*_cap")))
            if caps:
                return caps[0]
        return None

    def get_limits(self) -> TdpLimits:
        return self._fallback

    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        if not self.supported:
            return TdpResult(watts, None, False, "no steamdeck hwmon power cap found")
        target = self._fallback.clamp(watts)
        try:
            with open(self._cap, "w") as f:  # type: ignore[arg-type]
                f.write(str(target * 1_000_000))
        except OSError as e:
            return TdpResult(watts, self.read_applied(), False, f"hwmon write failed: {e}")
        applied = self.read_applied()
        ok = applied == target
        return TdpResult(watts, applied, ok, "" if ok else f"wanted {target}, read {applied}")

    def read_applied(self) -> int | None:
        try:
            with open(self._cap) as f:  # type: ignore[arg-type]
                return round(int(f.read().strip()) / 1_000_000)
        except (OSError, ValueError):
            return None
