"""Intel RAPL powercap TDP backend (MSI Claw and other Intel handhelds whose
kernel exposes no firmware-attributes ppt_*). Synthetic powercap sysfs."""
import os

from tdp.intel_rapl import IntelRaplBackend
from tdp.types import TdpLimits

_FALLBACK = TdpLimits(min_w=8, default_w=17, max_w=30, max_ac_w=30)


def _mk_rapl(root, base, pl1_uw=30_000_000, pl2_uw=37_000_000):
    d = os.path.join(root, "sys/devices/virtual/powercap", base)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "name"), "w") as f:
        f.write("package-0")
    with open(os.path.join(d, "constraint_0_power_limit_uw"), "w") as f:
        f.write(str(pl1_uw))
    with open(os.path.join(d, "constraint_1_power_limit_uw"), "w") as f:
        f.write(str(pl2_uw))
    return d


_MMIO = "intel-rapl-mmio/intel-rapl-mmio:0"
_LEGACY = "intel-rapl/intel-rapl:0"


def _read_uw(d, i):
    with open(os.path.join(d, f"constraint_{i}_power_limit_uw")) as f:
        return int(f.read().strip())


class TestIntelRapl:
    def test_unsupported_without_powercap(self, tmp_path):
        assert IntelRaplBackend(_FALLBACK, root=str(tmp_path)).supported is False

    def test_supported_with_mmio(self, tmp_path):
        _mk_rapl(str(tmp_path), _MMIO)
        assert IntelRaplBackend(_FALLBACK, root=str(tmp_path)).supported is True

    def test_prefers_mmio_over_legacy(self, tmp_path):
        _mk_rapl(str(tmp_path), _LEGACY)
        d_mmio = _mk_rapl(str(tmp_path), _MMIO)
        b = IntelRaplBackend(_FALLBACK, root=str(tmp_path))
        b.set_tdp(20, True)
        assert _read_uw(d_mmio, 0) == 20_000_000  # wrote to mmio, not legacy

    def test_set_tdp_writes_pl1_in_microwatts_and_reads_back(self, tmp_path):
        d = _mk_rapl(str(tmp_path), _MMIO)
        b = IntelRaplBackend(_FALLBACK, root=str(tmp_path))
        res = b.set_tdp(20, True)
        assert _read_uw(d, 0) == 20_000_000
        assert res.applied_w == 20
        assert res.ok is True

    def test_set_tdp_also_raises_pl2_boost(self, tmp_path):
        d = _mk_rapl(str(tmp_path), _MMIO)
        IntelRaplBackend(_FALLBACK, root=str(tmp_path)).set_tdp(20, True)
        assert _read_uw(d, 1) >= 20_000_000  # PL2 (constraint_1) >= PL1

    def test_set_tdp_clamps_to_fallback_max(self, tmp_path):
        d = _mk_rapl(str(tmp_path), _MMIO)
        b = IntelRaplBackend(_FALLBACK, root=str(tmp_path))
        res = b.set_tdp(999, True)
        assert _read_uw(d, 0) == 30_000_000  # clamped to max_ac_w=30
        assert res.applied_w == 30

    def test_read_applied_converts_uw_to_w(self, tmp_path):
        _mk_rapl(str(tmp_path), _MMIO, pl1_uw=25_000_000)
        assert IntelRaplBackend(_FALLBACK, root=str(tmp_path)).read_applied() == 25

    def test_unsupported_set_tdp_never_raises(self, tmp_path):
        res = IntelRaplBackend(_FALLBACK, root=str(tmp_path)).set_tdp(20, True)
        assert res.ok is False
