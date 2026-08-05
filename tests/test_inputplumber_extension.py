from pathlib import Path
from types import SimpleNamespace
import hashlib
import json

from controllers import inputplumber_extension as extension


def _result(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, returncode=returncode)


def _write_manifest(plugin, version, stock_hash, binary=b"patched"):
    artifact = plugin / f"bin/inputplumber-xbox-hd-v{version}"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(binary)
    Path(f"{artifact}.sha256").write_text(hashlib.sha256(binary).hexdigest())
    manifest = plugin / "assets/inputplumber/compatibility.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "schema": 1,
        "device": "rog_xbox_ally_x",
        "builds": [{
            "version": version,
            "upstream_commit": "b" * 40,
            "patch": f"assets/inputplumber/v{version}-xbox-hd.patch",
            "artifact": f"bin/inputplumber-xbox-hd-v{version}",
            "artifact_sha256": f"bin/inputplumber-xbox-hd-v{version}.sha256",
            "provenance": f"bin/inputplumber-xbox-hd-v{version}.provenance",
            "stock_sha256": [stock_hash],
            "verified_platforms": ["steamos-test-rc73xa"],
        }],
    }))
    return artifact


def test_extension_refuses_hhd_owner_without_system_mutation(tmp_path):
    calls = []

    result = extension.ensure(
        device_key="rog_xbox_ally_x",
        manager="hhd",
        plugin_dir=str(tmp_path),
        run=lambda args: calls.append(args),
    )

    assert result == {
        "available": False, "changed": False, "reason": "wrong_manager",
    }
    assert calls == []


def test_extension_refuses_other_devices_without_system_mutation(tmp_path):
    calls = []
    result = extension.ensure(
        "legion_go_2", "inputplumber", str(tmp_path),
        run=lambda args: calls.append(args),
    )
    assert result["reason"] == "wrong_device"
    assert calls == []


def test_extension_refuses_missing_versioned_artifact(tmp_path, monkeypatch):
    stock = tmp_path / "stock-inputplumber"
    stock.write_bytes(b"stock")
    stock_hash = hashlib.sha256(stock.read_bytes()).hexdigest()
    artifact = _write_manifest(tmp_path, "0.77.4", stock_hash)
    Path(f"{artifact}.sha256").unlink()
    monkeypatch.setattr(extension, "STOCK_PATH", str(stock))

    def run(args):
        if args == [str(stock), "--version"]:
            return _result("inputplumber 0.77.4\n")
        return _result()

    result = extension.ensure(
        "rog_xbox_ally_x", "inputplumber", str(tmp_path),
        run=run,
    )
    assert result == {
        "available": False, "changed": False, "reason": "not_bundled",
    }


def test_extension_refuses_tampered_bundle(tmp_path, monkeypatch):
    stock = tmp_path / "stock-inputplumber"
    stock.write_bytes(b"stock")
    stock_hash = hashlib.sha256(stock.read_bytes()).hexdigest()
    binary = _write_manifest(tmp_path, "0.77.4", stock_hash)
    Path(f"{binary}.sha256").write_text("0" * 64)
    monkeypatch.setattr(extension, "STOCK_PATH", str(stock))

    def run(args):
        if args == [str(stock), "--version"]:
            return _result("inputplumber 0.77.4\n")
        return _result()

    result = extension.ensure(
        "rog_xbox_ally_x", "inputplumber", str(tmp_path),
        run=run,
    )
    assert result["reason"] == "bundle_mismatch"


def test_extension_selects_the_exact_manifest_build(tmp_path, monkeypatch):
    plugin = tmp_path / "plugin"
    stock = tmp_path / "stock-inputplumber"
    stock.write_bytes(b"stock-0.77.5")
    stock_hash = hashlib.sha256(stock.read_bytes()).hexdigest()
    _write_manifest(plugin, "0.77.5", stock_hash)
    install_root = tmp_path / "var/lib/panel/inputplumber"
    dropin_dir = tmp_path / "etc/systemd/inputplumber.service.d"
    monkeypatch.setattr(extension, "STOCK_PATH", str(stock))
    monkeypatch.setattr(extension, "INSTALL_ROOT", str(install_root), raising=False)
    monkeypatch.setattr(extension, "DROPIN_DIR", str(dropin_dir))
    monkeypatch.setattr(
        extension, "DROPIN_PATH", str(dropin_dir / "90-panel-hd-haptics.conf")
    )

    def run(args):
        if args == [str(stock), "--version"]:
            return _result("inputplumber 0.77.5\n")
        if args[-2:] == ["tree", extension.SERVICE]:
            return _result("/org/shadowblip/InputPlumber/CompositeDevice0\n")
        if args[-1:] == ["XboxHdHapticsSupported"]:
            return _result("b true\n")
        return _result()

    result = extension.ensure(
        "rog_xbox_ally_x", "inputplumber", str(plugin), run=run
    )

    assert result == {
        "available": True,
        "changed": True,
        "reason": None,
        "version": "0.77.5",
    }
    assert (install_root / "0.77.5/inputplumber").read_bytes() == b"patched"


def test_extension_installs_versioned_dropin_and_passes_healthcheck(
    tmp_path, monkeypatch,
):
    plugin = Path(tmp_path) / "plugin"
    stock = Path(tmp_path) / "stock-inputplumber"
    stock.write_bytes(b"stock")
    stock_hash = hashlib.sha256(stock.read_bytes()).hexdigest()
    _write_manifest(plugin, "0.77.4", stock_hash)
    install_dir = Path(tmp_path) / "var/lib/panel/inputplumber/0.77.4"
    dropin_dir = Path(tmp_path) / "etc/systemd/inputplumber.service.d"
    monkeypatch.setattr(extension, "STOCK_PATH", str(stock))
    monkeypatch.setattr(extension, "INSTALL_ROOT", str(install_dir.parent))
    monkeypatch.setattr(extension, "DROPIN_DIR", str(dropin_dir))
    monkeypatch.setattr(
        extension, "DROPIN_PATH", str(dropin_dir / "90-panel-hd-haptics.conf")
    )
    calls = []

    def run(args):
        calls.append(args)
        if args == [str(stock), "--version"]:
            return _result("inputplumber 0.77.4\n")
        if args[-2:] == ["tree", "org.shadowblip.InputPlumber"]:
            return _result(
                "/org/shadowblip/InputPlumber/CompositeDevice0\n"
            )
        if args[-1:] == ["XboxHdHapticsSupported"]:
            return _result("b true\n")
        return _result()

    result = extension.ensure(
        "rog_xbox_ally_x", "inputplumber", str(plugin), run=run
    )

    assert result == {
        "available": True,
        "changed": True,
        "reason": None,
        "version": "0.77.4",
    }
    assert (install_dir / "inputplumber").read_bytes() == b"patched"
    assert (dropin_dir / "90-panel-hd-haptics.conf").read_text() == (
        "[Service]\nExecStart=\n"
        f"ExecStart={install_dir / 'inputplumber'}\n"
    )
    assert calls[-5:] == [
        [extension.SYSTEMCTL, "daemon-reload"],
        [extension.SYSTEMCTL, "restart", "inputplumber"],
        [extension.SYSTEMCTL, "is-active", "inputplumber"],
        [extension.BUSCTL, "tree", extension.SERVICE],
        [
            extension.BUSCTL, "get-property", extension.SERVICE,
            "/org/shadowblip/InputPlumber/CompositeDevice0",
            extension.FF_IFACE, "XboxHdHapticsSupported",
        ],
    ]


def test_restart_waits_for_composite_discovery(monkeypatch):
    sleeps = []
    tree_reads = 0
    monkeypatch.setattr(extension.time, "sleep", sleeps.append)

    def run(args):
        nonlocal tree_reads
        if args[-2:] == ["tree", "org.shadowblip.InputPlumber"]:
            tree_reads += 1
            if tree_reads < 3:
                return _result("")
            return _result(
                "/org/shadowblip/InputPlumber/CompositeDevice0\n"
            )
        if args[-1:] == ["XboxHdHapticsSupported"]:
            return _result("b true\n")
        return _result()

    assert extension._restart(run, require_extension=True) is True
    assert tree_reads == 3
    assert sleeps == [extension.HEALTHCHECK_INTERVAL] * 2


def test_extension_removes_owned_override_after_stock_version_changes(
    tmp_path, monkeypatch,
):
    plugin = Path(tmp_path) / "plugin"
    stock = Path(tmp_path) / "stock-inputplumber"
    stock.write_bytes(b"stock")
    stock_hash = hashlib.sha256(stock.read_bytes()).hexdigest()
    _write_manifest(plugin, "0.77.4", stock_hash)
    install_dir = Path(tmp_path) / "var/lib/panel/inputplumber/0.77.4"
    dropin_dir = Path(tmp_path) / "etc/systemd/inputplumber.service.d"
    dropin_dir.mkdir(parents=True)
    dropin = dropin_dir / "90-panel-hd-haptics.conf"
    dropin.write_text(
        "[Service]\nExecStart=\n"
        f"ExecStart={install_dir / 'inputplumber'}\n"
    )
    monkeypatch.setattr(extension, "STOCK_PATH", str(stock))
    monkeypatch.setattr(extension, "INSTALL_ROOT", str(install_dir.parent))
    monkeypatch.setattr(extension, "DROPIN_DIR", str(dropin_dir))
    monkeypatch.setattr(extension, "DROPIN_PATH", str(dropin))
    calls = []

    def run(args):
        calls.append(args)
        if args == [str(stock), "--version"]:
            return _result("inputplumber 0.77.5\n")
        return _result()

    result = extension.ensure(
        "rog_xbox_ally_x", "inputplumber", str(plugin), run=run
    )

    assert result == {
        "available": False,
        "changed": True,
        "reason": "unsupported_version",
    }
    assert not dropin.exists()
    assert [call[1:] for call in calls[-3:]] == [
        ["daemon-reload"], ["restart", "inputplumber"],
        ["is-active", "inputplumber"],
    ]


def test_uninstall_removes_only_owned_override_and_installed_artifacts(
    tmp_path, monkeypatch,
):
    plugin = tmp_path / "plugin"
    _write_manifest(plugin, "0.77.4", "4" * 64)
    install_dir = tmp_path / "var/lib/panel/inputplumber/0.77.4"
    install_dir.mkdir(parents=True)
    installed = install_dir / "inputplumber"
    staged = install_dir / "inputplumber.new"
    installed.write_bytes(b"patched")
    staged.write_bytes(b"staged")
    dropin = tmp_path / "90-panel-hd-haptics.conf"
    dropin.write_text("owned")
    monkeypatch.setattr(extension, "INSTALL_ROOT", str(install_dir.parent))
    monkeypatch.setattr(extension, "DROPIN_PATH", str(dropin))

    assert extension.uninstall(
        "another_device", str(plugin), run=lambda _args: _result()
    ) is True
    assert not dropin.exists()
    assert not installed.exists()
    assert not staged.exists()
    assert not install_dir.exists()


def test_failed_override_removal_restarts_previous_binary(tmp_path, monkeypatch):
    dropin = tmp_path / "90-panel-hd-haptics.conf"
    dropin.write_text("owned")
    monkeypatch.setattr(extension, "DROPIN_PATH", str(dropin))
    calls = []
    restart_attempts = 0

    def run(args):
        nonlocal restart_attempts
        calls.append(args)
        if args[-2:] == ["restart", "inputplumber"]:
            restart_attempts += 1
            return _result(returncode=1 if restart_attempts == 1 else 0)
        if args[-2:] == ["tree", "org.shadowblip.InputPlumber"]:
            return _result(
                "/org/shadowblip/InputPlumber/CompositeDevice0\n"
            )
        if args[-1:] == ["XboxHdHapticsSupported"]:
            return _result("b true\n")
        return _result()

    assert extension._remove_override(run) is False

    assert dropin.read_text() == "owned"
    assert restart_attempts == 2
    assert sum(call[-1:] == ["daemon-reload"] for call in calls) == 2
    assert [extension.SYSTEMCTL, "is-active", "inputplumber"] in calls
