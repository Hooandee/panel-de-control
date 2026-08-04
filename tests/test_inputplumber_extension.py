from pathlib import Path
from types import SimpleNamespace
import hashlib

from controllers import inputplumber_extension as extension


def _result(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, returncode=returncode)


def test_extension_refuses_other_devices_without_system_mutation(tmp_path):
    calls = []
    result = extension.ensure(
        "legion_go_2", str(tmp_path), run=lambda args: calls.append(args)
    )
    assert result["reason"] == "wrong_device"
    assert calls == []


def test_extension_refuses_missing_versioned_artifact(tmp_path):
    result = extension.ensure(
        "rog_xbox_ally_x", str(tmp_path), run=lambda _args: _result()
    )
    assert result == {
        "available": False, "changed": False, "reason": "not_bundled",
    }


def test_extension_refuses_tampered_bundle(tmp_path):
    binary = Path(tmp_path) / "bin/inputplumber-xbox-hd-v0.77.4"
    binary.parent.mkdir()
    binary.write_bytes(b"patched")
    Path(f"{binary}.sha256").write_text("0" * 64)

    result = extension.ensure(
        "rog_xbox_ally_x", str(tmp_path), run=lambda _args: _result()
    )
    assert result["reason"] == "bundle_mismatch"


def test_extension_installs_versioned_dropin_and_passes_healthcheck(
    tmp_path, monkeypatch,
):
    plugin = Path(tmp_path) / "plugin"
    binary = plugin / "bin/inputplumber-xbox-hd-v0.77.4"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"patched")
    expected = hashlib.sha256(b"patched").hexdigest()
    Path(f"{binary}.sha256").write_text(expected)
    stock = Path(tmp_path) / "stock-inputplumber"
    stock.write_bytes(b"stock")
    install_dir = Path(tmp_path) / "var/lib/panel/inputplumber/0.77.4"
    dropin_dir = Path(tmp_path) / "etc/systemd/inputplumber.service.d"
    monkeypatch.setattr(extension, "STOCK_PATH", str(stock))
    monkeypatch.setattr(
        extension, "STOCK_SHA256", hashlib.sha256(b"stock").hexdigest()
    )
    monkeypatch.setattr(extension, "INSTALL_DIR", str(install_dir))
    monkeypatch.setattr(
        extension, "INSTALL_PATH", str(install_dir / "inputplumber")
    )
    monkeypatch.setattr(extension, "DROPIN_DIR", str(dropin_dir))
    monkeypatch.setattr(
        extension, "DROPIN_PATH", str(dropin_dir / "90-panel-hd-haptics.conf")
    )
    calls = []

    def run(args):
        calls.append(args)
        if args == [str(stock), "--version"]:
            return _result("inputplumber 0.77.4\n")
        return _result()

    result = extension.ensure("rog_xbox_ally_x", str(plugin), run=run)

    assert result == {"available": True, "changed": True, "reason": None}
    assert (install_dir / "inputplumber").read_bytes() == b"patched"
    assert (dropin_dir / "90-panel-hd-haptics.conf").read_text() == (
        "[Service]\nExecStart=\n"
        f"ExecStart={install_dir / 'inputplumber'}\n"
    )
    assert [call[1:] for call in calls[-3:]] == [
        ["daemon-reload"], ["restart", "inputplumber"],
        ["is-active", "inputplumber"],
    ]
