import os

from device_profiles import DEVICE_TABLE, GENERIC
from device_quirks import is_gpd_win_mini_2025


def _profile(key):
    return next(profile for profile in DEVICE_TABLE if profile.key == key)


def _write_dmi(root: str, vendor: str, product: str) -> None:
    base = os.path.join(root, "sys/class/dmi/id")
    os.makedirs(base, exist_ok=True)
    for name, value in (("sys_vendor", vendor), ("product_name", product)):
        with open(os.path.join(base, name), "w") as handle:
            handle.write(value)


def test_exact_gpd_win_mini_2025_match_is_case_insensitive(tmp_path):
    _write_dmi(str(tmp_path), "gPd", "g1617-02")

    assert is_gpd_win_mini_2025(
        _profile("gpd_win_mini_2025"),
        str(tmp_path),
    )


def test_gpd_quirk_rejects_nearby_or_generic_identity(tmp_path):
    cases = (
        ("OTHER", "G1617-02", _profile("gpd_win_mini_2025")),
        ("GPD", "G1617-01", _profile("gpd_win_mini_2025")),
        ("GPD", "G1617-02-L", _profile("gpd_win_mini_2025")),
        ("GPD", "prefix-G1617-02-suffix", _profile("gpd_win_mini_2025")),
        ("GPD", "G1617-02", GENERIC),
    )

    for vendor, product, profile in cases:
        _write_dmi(str(tmp_path), vendor, product)
        assert not is_gpd_win_mini_2025(profile, str(tmp_path))


def test_gpd_quirk_is_false_when_dmi_is_unreadable(tmp_path):
    assert not is_gpd_win_mini_2025(
        _profile("gpd_win_mini_2025"),
        str(tmp_path),
    )
