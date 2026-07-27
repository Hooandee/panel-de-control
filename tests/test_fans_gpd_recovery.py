import json
import os
from types import SimpleNamespace

from device_profiles import DEVICE_TABLE, GENERIC
from fans.gpd_recovery import ensure_gpd_fan, gpdfan_abi_complete


GPD = next(profile for profile in DEVICE_TABLE if profile.key == "gpd_win_mini_2025")


def _write(path: str, content: str = "") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(content)


def _exact_gpd_root(tmp_path) -> str:
    root = str(tmp_path)
    base = os.path.join(root, "sys/class/dmi/id")
    _write(os.path.join(base, "sys_vendor"), "GPD\n")
    _write(os.path.join(base, "product_name"), "G1617-02\n")
    return root


def _make_gpdfan(root: str, *, complete: bool) -> None:
    base = os.path.join(root, "sys/class/hwmon/hwmon7")
    _write(os.path.join(base, "name"), "gpdfan\n")
    _write(os.path.join(base, "fan1_input"), "2100\n")
    _write(os.path.join(base, "pwm1"), "120\n")
    if complete:
        _write(os.path.join(base, "pwm1_enable"), "2\n")


class _Runner:
    def __init__(self, returncode: int):
        self.returncode = returncode
        self.calls = []

    def __call__(self, command):
        self.calls.append(command)
        return SimpleNamespace(returncode=self.returncode)


class _WaitThatCreatesAbi:
    def __init__(self, root: str):
        self.root = root
        self.calls = 0

    def __call__(self, check):
        self.calls += 1
        _make_gpdfan(self.root, complete=True)
        return check()


def test_other_model_never_runs_modprobe(tmp_path):
    runner = _Runner(returncode=0)
    outcome = ensure_gpd_fan(GENERIC, root=str(tmp_path), run=runner)
    assert outcome["eligible"] is False
    assert runner.calls == []


def test_matching_profile_with_wrong_dmi_never_runs_modprobe(tmp_path):
    root = str(tmp_path)
    _write(os.path.join(root, "sys/class/dmi/id/sys_vendor"), "OTHER\n")
    _write(os.path.join(root, "sys/class/dmi/id/product_name"), "G1617-02\n")
    runner = _Runner(returncode=0)
    outcome = ensure_gpd_fan(GPD, root=root, run=runner)
    assert outcome["eligible"] is False
    assert runner.calls == []


def test_existing_complete_abi_is_noop(tmp_path):
    root = _exact_gpd_root(tmp_path)
    _make_gpdfan(root, complete=True)
    runner = _Runner(returncode=0)
    outcome = ensure_gpd_fan(GPD, root=root, run=runner)
    assert outcome["abi_before"] is True
    assert outcome["attempted"] is False
    assert outcome["abi_after"] is True
    assert runner.calls == []


def test_successful_modprobe_waits_for_complete_abi(tmp_path):
    root = _exact_gpd_root(tmp_path)
    runner = _Runner(returncode=0)
    wait = _WaitThatCreatesAbi(root)
    outcome = ensure_gpd_fan(
        GPD,
        root=root,
        run=runner,
        wait_for_abi=wait,
    )
    assert runner.calls == [["modprobe", "gpd_fan"]]
    assert wait.calls == 1
    assert outcome["abi_after"] is True


def test_nonzero_modprobe_stays_incomplete_without_waiting(tmp_path):
    root = _exact_gpd_root(tmp_path)
    runner = _Runner(returncode=1)
    wait_calls = []
    outcome = ensure_gpd_fan(
        GPD,
        root=root,
        run=runner,
        wait_for_abi=lambda check: wait_calls.append(check),
    )
    assert outcome["exit"] == 1
    assert outcome["abi_after"] is False
    assert wait_calls == []


def test_partial_abi_is_not_supported(tmp_path):
    root = _exact_gpd_root(tmp_path)
    _make_gpdfan(root, complete=False)
    assert gpdfan_abi_complete(root) is False


def test_nodes_from_different_hwmon_chips_do_not_form_an_abi(tmp_path):
    root = _exact_gpd_root(tmp_path)
    first = os.path.join(root, "sys/class/hwmon/hwmon1")
    second = os.path.join(root, "sys/class/hwmon/hwmon2")
    _write(os.path.join(first, "name"), "gpdfan\n")
    _write(os.path.join(first, "fan1_input"), "2100\n")
    _write(os.path.join(second, "name"), "gpdfan\n")
    _write(os.path.join(second, "pwm1"), "120\n")
    _write(os.path.join(second, "pwm1_enable"), "2\n")
    assert gpdfan_abi_complete(root) is False


def test_runner_exception_is_sanitized(tmp_path):
    root = _exact_gpd_root(tmp_path)

    def raise_private_error(command):
        raise RuntimeError("/home/private stderr=secret")

    outcome = ensure_gpd_fan(GPD, root=root, run=raise_private_error)
    assert outcome["error"] == "RuntimeError"
    encoded = json.dumps(outcome)
    assert "private" not in encoded
    assert "secret" not in encoded


def test_outcome_schema_is_fixed_for_ineligible_device(tmp_path):
    outcome = ensure_gpd_fan(GENERIC, root=str(tmp_path), run=_Runner(returncode=0))
    assert set(outcome) == {
        "eligible",
        "abi_before",
        "attempted",
        "exit",
        "error",
        "abi_after",
    }
