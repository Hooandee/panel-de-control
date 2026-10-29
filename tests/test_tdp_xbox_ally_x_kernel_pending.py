import os

import pytest

from device_profiles import DEVICE_TABLE
from tdp.factory import select_backend
from tdp.reconcile import build_targets


_NO_RYZENADJ = lambda: None  # noqa: E731
_LEGACY = "sys/devices/platform/asus-nb-wmi"
_ARMOURY = "sys/class/firmware-attributes/asus-armoury/attributes"


def _p(key):
    return next(x for x in DEVICE_TABLE if x.key == key)


def _mk_dmi(root, vendor, product, board):
    base = os.path.join(root, "sys/class/dmi/id")
    os.makedirs(base, exist_ok=True)
    for name, value in (
        ("sys_vendor", vendor),
        ("product_name", product),
        ("board_name", board),
    ):
        with open(os.path.join(base, name), "w") as handle:
            handle.write(value)


def _mk_legacy(root, watts=17):
    base = os.path.join(root, _LEGACY)
    os.makedirs(base, exist_ok=True)
    for name in ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_fppt"):
        with open(os.path.join(base, name), "w") as handle:
            handle.write(str(watts))


def _mk_armoury_without_limits(root):
    # #1012: Anatase 7.2.7 has no RC74XA power_limits entry; asus-armoury still
    # registers the ppt attributes but none of their values can be read.
    for attr in ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"):
        for name in ("current_value", "min_value", "max_value"):
            # Present but unreadable: a directory makes open() fail like the kernel does.
            os.makedirs(os.path.join(root, _ARMOURY, attr, name), exist_ok=True)


def _mk_armoury_with_limits(root, mins=(7, 13, 19), maxes=(35, 45, 55), current=17):
    for attr, mn, mx in zip(
        ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"), mins, maxes
    ):
        base = os.path.join(root, _ARMOURY, attr)
        os.makedirs(base, exist_ok=True)
        for name, value in (
            ("current_value", current),
            ("min_value", mn),
            ("max_value", mx),
        ):
            with open(os.path.join(base, name), "w") as handle:
                handle.write(str(value))


def _read_legacy(root):
    out = {}
    for rail, name in (
        ("pl1", "ppt_pl1_spl"),
        ("pl2", "ppt_pl2_sppt"),
        ("pl3", "ppt_fppt"),
    ):
        with open(os.path.join(root, _LEGACY, name)) as handle:
            out[rail] = int(handle.read().strip())
    return out


def _rc74xa(root):
    _mk_dmi(root, "ASUS", "ROG XBOX Ally X RC74XA RC74XA", "RC74XA")


def _select(root, key="rog_xbox_ally_x"):
    return select_backend(_p(key), root=root, ryzenadj_resolve=_NO_RYZENADJ)


def test_xbox_ally_x_20_legacy_fallback_keeps_firmware_rail_minimums(tmp_path):
    root = str(tmp_path)
    _rc74xa(root)
    _mk_armoury_without_limits(root)
    _mk_legacy(root)

    backend = _select(root)
    result = backend.set_levels(17, 17, 17, ac=False)

    assert backend.name == "asus-nb-wmi"
    assert result.ok is True
    assert backend.hidden_overshoot_guard is True
    assert _read_legacy(root) == {"pl1": 17, "pl2": 17, "pl3": 19}
    limits = backend.level_limits()
    assert (limits["pl1"]["min"], limits["pl2"]["min"], limits["pl3"]["min"]) == (7, 13, 19)


def test_raised_boost_rails_read_as_a_boost_floor_not_a_device_minimum(tmp_path):
    root = str(tmp_path)
    _rc74xa(root)
    _mk_armoury_without_limits(root)
    _mk_legacy(root)
    backend = _select(root)

    targets = build_targets(
        {"pl1": 17, "pl2": 17, "pl3": 17},
        backend.level_limits(),
        backend.observe(),
    )

    assert targets.target == {"pl1": 17, "pl2": 17, "pl3": 19}
    assert targets.reasons == {"pl3": "safe_min"}


def test_xbox_ally_x_20_legacy_fallback_lifts_low_requests_to_minimums(tmp_path):
    root = str(tmp_path)
    _rc74xa(root)
    _mk_armoury_without_limits(root)
    _mk_legacy(root)

    backend = _select(root)

    assert backend.set_tdp(7, ac=False).ok is True
    assert _read_legacy(root) == {"pl1": 7, "pl2": 13, "pl3": 19}


def test_xbox_ally_x_legacy_fallback_reports_kernel_without_power_limits(tmp_path):
    root = str(tmp_path)
    _rc74xa(root)
    _mk_armoury_without_limits(root)
    _mk_legacy(root)

    backend = _select(root)

    assert backend.kernel_power_limits_missing is True
    assert backend.diagnostics()["kernel_power_limits_missing"] is True


def test_legacy_only_kernel_is_not_reported_as_missing_power_limits(tmp_path):
    root = str(tmp_path)
    _mk_dmi(root, "ASUSTeK COMPUTER INC.", "ROG Ally RC71L_RC71L", "RC71L")
    _mk_legacy(root, watts=15)

    backend = _select(root, "rog_ally")

    assert backend.name == "asus-nb-wmi"
    assert backend.kernel_power_limits_missing is False


def test_other_ally_models_keep_their_legacy_rails_unchanged(tmp_path):
    root = str(tmp_path)
    _mk_dmi(root, "ASUSTeK COMPUTER INC.", "ROG Ally RC71L_RC71L", "RC71L")
    _mk_armoury_without_limits(root)
    _mk_legacy(root, watts=15)

    backend = _select(root, "rog_ally")
    backend.set_tdp(7, ac=False)

    assert _read_legacy(root) == {"pl1": 7, "pl2": 7, "pl3": 7}
    assert backend.hidden_overshoot_guard is False
    limits = backend.level_limits()
    assert {limits[rail]["min"] for rail in limits} == {7}


@pytest.mark.parametrize(
    ("board", "product"),
    (
        ("RC73XA", "ROG Xbox Ally X RC73XA_RC73XA"),
        ("RC75XA", "ROG XBOX Ally X RC75XA RC75XA"),
    ),
)
def test_other_xbox_ally_x_boards_keep_legacy_rails(tmp_path, board, product):
    root = str(tmp_path)
    _mk_dmi(root, "ASUS", product, board)
    _mk_armoury_without_limits(root)
    _mk_legacy(root)

    backend = _select(root)
    backend.set_tdp(7, ac=False)

    assert _read_legacy(root) == {"pl1": 7, "pl2": 7, "pl3": 7}
    assert backend.hidden_overshoot_guard is False
    assert backend.thermal_policy_reassert is False


def test_kernel_with_rc74xa_power_limits_moves_to_asus_armoury(tmp_path):
    root = str(tmp_path)
    _rc74xa(root)
    _mk_armoury_with_limits(root)
    _mk_legacy(root)

    backend = _select(root)

    assert backend.name == "firmware-attr:asus-armoury"
    assert getattr(backend, "kernel_power_limits_missing", False) is False


def _mk_thermal_policy(root, value=0):
    path = os.path.join(root, _LEGACY, "throttle_thermal_policy")
    with open(path, "w") as handle:
        handle.write(f"{value}\n")
    return path


def test_xbox_ally_x_20_legacy_fallback_rewrites_the_same_thermal_policy(tmp_path):
    root = str(tmp_path)
    _rc74xa(root)
    _mk_armoury_without_limits(root)
    _mk_legacy(root)
    path = _mk_thermal_policy(root, 1)

    backend = _select(root)

    assert backend.thermal_policy_reassert is True
    assert backend.read_thermal_policy() == 1
    assert backend.reassert_thermal_policy() == {"ok": True, "policy": 1, "readback": 1}
    with open(path) as handle:
        assert handle.read().strip() == "1"


def test_thermal_policy_step_needs_the_node_and_the_board(tmp_path):
    no_node = str(tmp_path / "no-node")
    _rc74xa(no_node)
    _mk_armoury_without_limits(no_node)
    _mk_legacy(no_node)

    other = str(tmp_path / "other")
    _mk_dmi(other, "ASUSTeK COMPUTER INC.", "ROG Ally RC71L_RC71L", "RC71L")
    _mk_legacy(other, watts=15)
    _mk_thermal_policy(other)

    assert _select(no_node).thermal_policy_reassert is False
    assert _select(no_node).reassert_thermal_policy()["ok"] is False
    assert _select(other, "rog_ally").thermal_policy_reassert is False
