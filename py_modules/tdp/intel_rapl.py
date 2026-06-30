import os

from tdp.backend import TDPBackend
from tdp.types import TdpLimits, TdpResult

_POWERCAP = "sys/devices/virtual/powercap"
# Prefer the MMIO interface (current on recent kernels), fall back to the legacy one.
_RAPL_DIRS = ("intel-rapl-mmio/intel-rapl-mmio:0", "intel-rapl/intel-rapl:0")

# PL2 (constraint_1) boost above the sustained PL1 when a single TDP value is set.
_PL2_BOOST_RATIO = 1.25


class IntelRaplBackend(TDPBackend):
    """TDP for Intel handhelds (MSI Claw) via the powercap RAPL interface:
    ``constraint_0_power_limit_uw`` = sustained PL1, ``constraint_1`` = PL2 (µW).

    Used when the kernel exposes no MSI firmware-attributes ppt_* (the case on
    current Bazzite/Neptune kernels). Limits come from the device profile — RAPL's
    ``constraint_0_max_power_uw`` underreports (rated TDP, not the writable ceiling).
    Never raises.
    """

    name = "intel-rapl"
    supports_levels = False  # PL1 (+ derived PL2 boost); no manual per-rail UI for now

    def __init__(self, fallback: TdpLimits, root: str = "/") -> None:
        self._fallback = fallback
        self._root = root
        self._dir = self._find_rapl_dir()
        self.supported = self._dir is not None

    def _find_rapl_dir(self):
        for base in _RAPL_DIRS:
            d = os.path.join(self._root, _POWERCAP, base)
            if os.path.exists(os.path.join(d, "constraint_0_power_limit_uw")):
                return d
        return None

    def _constraint(self, i: int) -> str:
        return os.path.join(self._dir or "", f"constraint_{i}_power_limit_uw")

    def _read_int(self, path):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def _write(self, path, value) -> bool:
        try:
            with open(path, "w") as f:
                f.write(str(value))
            return True
        except OSError:
            return False

    def get_limits(self) -> TdpLimits:
        return self._fallback

    def set_tdp(self, watts: int, ac: bool) -> TdpResult:
        if not self.supported:
            return TdpResult(watts, None, False, "intel-rapl powercap not present")
        target = self._fallback.clamp(watts, ac)
        pl2 = max(target, round(target * _PL2_BOOST_RATIO))
        # Raise PL2 first so PL1 is never transiently above PL2.
        self._write(self._constraint(1), pl2 * 1_000_000)
        ok = self._write(self._constraint(0), target * 1_000_000)
        applied = self.read_applied()
        # RAPL quantizes the limit to the package power-unit granularity, so the
        # readback can round to target±1 W even on a good write — accept ±1 W.
        success = ok and applied is not None and abs(applied - target) <= 1
        detail = "" if success else f"write not confirmed (wanted {target}, read {applied})"
        return TdpResult(target, applied, success, detail)

    def read_applied(self) -> int | None:
        uw = self._read_int(self._constraint(0))
        return round(uw / 1_000_000) if uw is not None else None
