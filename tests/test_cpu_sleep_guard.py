import os
import subprocess

import pytest

from cpu.sleep_guard import UNIT_NAME, UNIT_TEXT, SleepCoreGuard


def _guard(tmp_path, ok=True):
    calls = []

    def systemctl(*args):
        calls.append(args)
        return ok

    return SleepCoreGuard(root=str(tmp_path), systemctl=systemctl), calls


def test_installs_a_runtime_unit_wanted_by_sleep_target(tmp_path):
    guard, calls = _guard(tmp_path)
    assert guard.ensure() is True
    unit = tmp_path / "run/systemd/system" / UNIT_NAME
    link = tmp_path / "run/systemd/system/sleep.target.wants" / UNIT_NAME
    assert unit.read_text() == UNIT_TEXT
    assert os.readlink(link) == os.path.join("..", UNIT_NAME)
    assert "Before=sleep.target" in UNIT_TEXT
    assert calls == [("daemon-reload",)]
    assert guard.installed


def test_ensure_does_not_reload_systemd_again(tmp_path):
    guard, calls = _guard(tmp_path)
    guard.ensure()
    guard.ensure()
    assert calls == [("daemon-reload",)]


def test_remove_cleans_up_and_reloads_only_when_present(tmp_path):
    guard, calls = _guard(tmp_path)
    assert guard.remove() is True
    assert calls == []
    guard.ensure()
    assert guard.remove() is True
    assert not guard.installed
    assert not (tmp_path / "run/systemd/system" / UNIT_NAME).exists()
    assert calls == [("daemon-reload",), ("daemon-reload",)]


def test_failed_reload_is_reported_and_retried(tmp_path):
    results = iter([False, True])
    calls = []

    def systemctl(*args):
        calls.append(args)
        return next(results)

    guard = SleepCoreGuard(root=str(tmp_path), systemctl=systemctl)
    assert guard.ensure() is False
    assert guard.diagnostics() == {"installed": True, "loaded": False, "last_error": "daemon_reload_failed"}
    assert guard.ensure() is True
    assert guard.ready and calls == [("daemon-reload",), ("daemon-reload",)]


def test_unit_script_onlines_only_offline_cpus(tmp_path):
    """The ExecStart line, with systemd's $$ unescaped, run against a fake sysfs."""
    cpu = tmp_path / "sys/devices/system/cpu"
    for index, state in ((1, "0"), (2, "1"), (3, "0")):
        (cpu / f"cpu{index}").mkdir(parents=True)
        (cpu / f"cpu{index}" / "online").write_text(state)
    line = next(row for row in UNIT_TEXT.splitlines() if row.startswith("ExecStart="))
    script = line.split("-c '", 1)[1].rsplit("'", 1)[0].replace("$$", "$")
    script = script.replace("/sys/devices/system/cpu", str(cpu))
    subprocess.run(["/bin/sh", "-c", script], check=True)
    assert [(cpu / f"cpu{i}" / "online").read_text().strip() for i in (1, 2, 3)] == ["1", "1", "1"]


def test_remove_without_reload_keeps_unload_fast(tmp_path):
    guard, calls = _guard(tmp_path)
    guard.ensure()
    assert guard.remove(reload=False) is True
    assert not guard.installed
    assert calls == [("daemon-reload",)]


@pytest.mark.parametrize("active_cores", [4, 8])
def test_sleep_unit_enables_smt_with_limited_or_all_physical_cores(tmp_path, active_cores):
    cpu = tmp_path / "sys/devices/system/cpu"
    (cpu / "smt").mkdir(parents=True)
    (cpu / "smt/control").write_text("off")
    (cpu / "smt/active").write_text("1\n")
    for index in range(1, 16):
        (cpu / f"cpu{index}").mkdir()
        online = index < active_cores
        (cpu / f"cpu{index}/online").write_text("1" if online else "0")
    line = next(row for row in UNIT_TEXT.splitlines() if row.startswith("ExecStart="))
    script = line.split("-c '", 1)[1].rsplit("'", 1)[0].replace("$$", "$")
    script = script.replace("/sys/devices/system/cpu", str(cpu))
    result = subprocess.run(["/bin/sh", "-c", script], check=True, capture_output=True, text=True)
    assert result.stdout.strip() == "pdc-sleep-cores rc=0 smt_active=1"
    assert (cpu / "smt/control").read_text().strip() == "on"
    assert all((cpu / f"cpu{i}/online").read_text().strip() == "1" for i in range(1, 16))


@pytest.mark.parametrize("mode", ["on", "forceoff", "notsupported"])
def test_sleep_unit_preserves_other_smt_states(tmp_path, mode):
    cpu = tmp_path / "sys/devices/system/cpu"
    (cpu / "smt").mkdir(parents=True)
    (cpu / "smt/control").write_text(mode)
    line = next(row for row in UNIT_TEXT.splitlines() if row.startswith("ExecStart="))
    script = line.split("-c '", 1)[1].rsplit("'", 1)[0].replace("$$", "$")
    subprocess.run(["/bin/sh", "-c", script.replace("/sys/devices/system/cpu", str(cpu))], check=True)
    assert (cpu / "smt/control").read_text().strip() == mode
