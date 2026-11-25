import hashlib
import io
import tarfile
from types import SimpleNamespace

import json
from pathlib import Path

import pytest
from test_upscalers_mako import setup
from upscalers import mako



def release(manager):
    archive = manager.home.parent / "mako-next.tar.xz"
    with tarfile.open(archive, "w:xz") as handle:
        for name in mako.PAYLOAD:
            content = b"new renderer content " + name.encode()
            info = tarfile.TarInfo(name)
            info.size = len(content)
            handle.addfile(info, io.BytesIO(content))
    return SimpleNamespace(ensure=lambda *args: archive), SimpleNamespace(sha256=hashlib.sha256(archive.read_bytes()).hexdigest())


def test_future_base_version_keeps_the_existing_launch_path(setup, monkeypatch):
    manager, _, _, _ = setup
    monkeypatch.setattr(mako, "VERSION", "4.7.0")
    upgraded = mako.Mako(str(manager.home), manager.manifest_path.parent)
    assert upgraded.prefix == manager.prefix


def test_upgrade_keeps_existing_launcher_and_profiles(setup):
    manager, cache, _, calls = setup
    manager.install(cache)
    launch = manager.set_game("123", "game", {"target_fps": 87, "mode": "adaptive"})
    config = Path(launch["env"]["MAKO_CONFIG"])
    before = config.read_bytes()
    guards = []
    next_cache, asset = release(manager)
    result = manager.install(next_cache, asset=asset, version="4.6.1", before_commit=lambda: guards.append(True))
    assert guards == [True]
    assert result["version"] == "4.6.1"
    assert config.read_bytes() == before
    assert result["profiles"]["123"]["target_fps"] == 87
    assert Path(launch["wrappers"][0]).read_bytes().startswith(b"new renderer content")
    assert any(".mako-" in args[0] and args[1] == "validate" for args in calls)
    assert manager.report()["component"]["id"] == "mako-render-4.6.1"


def test_upgrade_deferred_at_commit_keeps_old_motor(setup):
    manager, cache, _, _ = setup
    manager.install(cache)
    before = manager.manifest_path.read_bytes()
    def defer():
        raise RuntimeError("engine_deferred")
    next_cache, asset = release(manager)
    with pytest.raises(RuntimeError, match="engine_deferred"):
        manager.install(next_cache, asset=asset, version="4.6.1", before_commit=defer)
    assert manager.manifest_path.read_bytes() == before
    assert manager.status()["version"] == "4.6.0"
    manager._verify_install(manager._state())


def test_upgrade_rejected_profile_keeps_old_motor(setup, monkeypatch):
    manager, cache, _, _ = setup
    manager.install(cache)
    manager.set_game("123", "game", {})
    before = manager.manifest_path.read_bytes()
    def invalid(*args, **kwargs):
        raise mako.MakoError("mako_config_invalid")
    monkeypatch.setattr(manager, "_validate", invalid)
    next_cache, asset = release(manager)
    with pytest.raises(mako.MakoError, match="mako_config_invalid"):
        manager.install(next_cache, asset=asset, version="4.6.1")
    assert manager.manifest_path.read_bytes() == before
    manager._verify_install(manager._state())


def test_upgrade_manifest_failure_restores_previous_install(setup, monkeypatch):
    manager, cache, _, _ = setup
    manager.install(cache)
    before = manager.manifest_path.read_bytes()
    def fail(state):
        raise OSError("disk full")
    monkeypatch.setattr(manager, "_save", fail)
    next_cache, asset = release(manager)
    with pytest.raises(mako.MakoError, match="mako_write_failed"):
        manager.install(next_cache, asset=asset, version="4.6.1")
    assert manager.manifest_path.read_bytes() == before
    manager._verify_install(manager._state())


def test_backup_cleanup_failure_does_not_report_failed_update(setup, monkeypatch):
    manager, cache, _, _ = setup
    manager.install(cache)
    original = mako.shutil.rmtree
    def fail_backup(path, *args, **kwargs):
        if str(path).endswith("-previous"):
            raise OSError("cleanup unavailable")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(mako.shutil, "rmtree", fail_backup)
    assert manager.install(cache, version="4.6.1")["version"] == "4.6.1"
    manager._verify_install(manager._state())


def test_rollback_restores_old_motor_before_failed_cleanup(setup, monkeypatch):
    manager, cache, _, _ = setup
    manager.install(cache)
    before = manager.manifest_path.read_bytes()
    next_cache, asset = release(manager)
    def fail_save(state):
        raise OSError('disk full')
    def fail_cleanup(path):
        raise OSError('cleanup unavailable')
    monkeypatch.setattr(manager, '_save', fail_save)
    monkeypatch.setattr(mako.shutil, 'rmtree', fail_cleanup)
    with pytest.raises(mako.MakoError, match='mako_write_failed'):
        manager.install(next_cache, asset=asset, version='4.6.1')
    assert manager.manifest_path.read_bytes() == before
    manager._verify_install(manager._state())


def test_failed_restore_reports_error_and_preserves_old_backup(setup, monkeypatch):
    manager, cache, _, _ = setup
    manager.install(cache)
    before = manager.manifest_path.read_bytes()
    old_files = {name: (manager.prefix / name).read_bytes() for name in mako.PAYLOAD}
    next_cache, asset = release(manager)
    rename = Path.rename
    def fail_save(state):
        raise OSError('disk full')
    def fail_restore(path, target):
        if path.name.endswith('-previous'):
            raise OSError('restore unavailable')
        return rename(path, target)
    monkeypatch.setattr(manager, '_save', fail_save)
    monkeypatch.setattr(Path, 'rename', fail_restore)
    with pytest.raises(mako.MakoError, match='mako_restore_failed'):
        manager.install(next_cache, asset=asset, version='4.6.1')
    assert manager.manifest_path.read_bytes() == before
    backups = list(manager.prefix.parent.glob('*-previous'))
    assert len(backups) == 1
    assert {name: (backups[0] / name).read_bytes() for name in mako.PAYLOAD} == old_files
