import os

from tdp.steamdeck_hwmon import SteamDeckHwmonBackend
from tdp.types import TdpLimits

FALLBACK = TdpLimits(min_w=3, default_w=12, max_w=15, max_ac_w=15)


def _mk_hwmon(root, idx, name, cap_file="power1_cap", cap_uw="15000000"):
    d = os.path.join(root, "sys/class/hwmon", f"hwmon{idx}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "name"), "w") as f:
        f.write(name)
    with open(os.path.join(d, cap_file), "w") as f:
        f.write(cap_uw)
    return os.path.join(d, cap_file)


def test_unsupported_when_no_hwmon(tmp_path):
    b = SteamDeckHwmonBackend(FALLBACK, root=str(tmp_path))
    assert b.supported is False


def test_finds_steamdeck_hwmon_among_others(tmp_path):
    root = str(tmp_path)
    _mk_hwmon(root, 0, "nvme")
    _mk_hwmon(root, 1, "steamdeck_hwmon")
    b = SteamDeckHwmonBackend(FALLBACK, root=root)
    assert b.supported is True


def test_set_tdp_writes_microwatts_and_reads_back(tmp_path):
    root = str(tmp_path)
    cap = _mk_hwmon(root, 0, "steamdeck_hwmon")
    b = SteamDeckHwmonBackend(FALLBACK, root=root)
    res = b.set_tdp(12, ac=False)
    assert res.ok is True and res.applied_w == 12
    assert open(cap).read().strip() == "12000000"
    assert b.read_applied() == 12


def test_set_tdp_clamps_to_limits(tmp_path):
    root = str(tmp_path)
    _mk_hwmon(root, 0, "steamdeck_hwmon")
    b = SteamDeckHwmonBackend(FALLBACK, root=root)
    assert b.set_tdp(99, ac=False).applied_w == 15
    assert b.set_tdp(1, ac=False).applied_w == 3
