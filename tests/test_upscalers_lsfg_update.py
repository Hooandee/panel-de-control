from pathlib import Path
from unittest.mock import patch

import pytest

from upscalers import lsfg


def payload(root, content):
    for name in lsfg.LAYER_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content + name.encode())
    return root


@pytest.fixture
def installed(tmp_path):
    engine = lsfg.Lsfg(str(tmp_path / 'home'), tmp_path / 'state')
    engine.install(payload(tmp_path / 'old', b'old'), 'old')
    engine.set_game('10', 'Game', {'multiplier': 3})
    engine.set_game('11', 'Paused', {})
    engine.set_game('11', 'Paused', None)
    return engine, payload(tmp_path / 'new', b'new')


def snapshot(engine):
    paths = [engine.local / name for name in lsfg.LAYER_FILES]
    paths += [engine.config_path, engine.manifest_path]
    return {path: path.read_bytes() if path.exists() else None for path in paths}


def test_update_preserves_profiles_and_reports_version(installed):
    engine, new = installed
    before = engine._manifest()
    result = engine.install(new, 'new')
    assert result['version'] == 'new'
    assert engine._manifest()['profiles'] == before['profiles']
    assert engine._manifest()['paused'] == before['paused']
    for name in lsfg.LAYER_FILES:
        assert (engine.local / name).read_bytes() == (new / name).read_bytes()


@pytest.mark.parametrize('method', ['_save', '_write_config'])
def test_failure_restores_all_previous_bytes(installed, method):
    engine, new = installed
    if method == '_write_config':
        engine.config_path.unlink()
    before = snapshot(engine)
    original = getattr(engine, method)
    def fail_after_write(*args):
        original(*args)
        raise OSError('disk failure')
    with patch.object(engine, method, side_effect=fail_after_write):
        with pytest.raises(lsfg.LsfgError):
            engine.install(new, 'new')
    assert snapshot(engine) == before


def test_checks_whole_archive_before_writing(installed):
    engine, new = installed
    (new / lsfg.LAYER_FILES[-1]).unlink()
    before = snapshot(engine)
    with pytest.raises(lsfg.LsfgError):
        engine.install(new, 'new')
    assert snapshot(engine) == before


def test_deferral_after_staging_keeps_previous_install(installed):
    engine, new = installed
    before = snapshot(engine)
    def defer():
        assert snapshot(engine) == before
        raise RuntimeError('running')
    with pytest.raises(RuntimeError, match='running'):
        engine.install(new, 'new', before_commit=defer)
    assert snapshot(engine) == before


@pytest.mark.parametrize('kind', ['modified', 'target_symlink', 'source_symlink'])
def test_refuses_changed_ownership_and_symlinks(installed, kind):
    engine, new = installed
    target = engine.local / lsfg.LAYER_FILES[0]
    source = new / lsfg.LAYER_FILES[0]
    if kind == 'modified':
        target.write_bytes(b'foreign edit')
    else:
        path = target if kind == 'target_symlink' else source
        saved = path.with_suffix('.real')
        path.rename(saved)
        path.symlink_to(saved)
    before = snapshot(engine)
    with pytest.raises(lsfg.LsfgError):
        engine.install(new, 'new')
    assert snapshot(engine) == before


@pytest.mark.parametrize('fail_at', range(1, 6))
def test_publish_failure_restores_replaced_library(installed, fail_at):
    engine, new = installed
    before = snapshot(engine)
    import os
    original = os.replace
    count = 0
    def fail_once(source, destination):
        nonlocal count
        count += 1
        if count == fail_at:
            raise OSError('disk failure')
        return original(source, destination)
    with patch.object(lsfg.os, 'replace', side_effect=fail_once):
        with pytest.raises(lsfg.LsfgError):
            engine.install(new, 'new')
    assert snapshot(engine) == before


def test_failed_first_install_leaves_no_installation(tmp_path):
    engine = lsfg.Lsfg(str(tmp_path / 'home'), tmp_path / 'state')
    new = payload(tmp_path / 'new', b'new')
    before = snapshot(engine)
    with patch.object(engine, '_write_config', side_effect=OSError('disk failure')):
        with pytest.raises(lsfg.LsfgError):
            engine.install(new, 'new')
    assert snapshot(engine) == before
    assert not list(engine.home.rglob('.lsfg-*'))


def test_update_does_not_truncate_open_library(installed):
    engine, new = installed
    path = engine.local / lsfg.LAYER_FILES[0]
    old = path.read_bytes()
    with path.open('rb') as existing_handle:
        engine.install(new, 'new')
        assert existing_handle.read() == old
    assert path.read_bytes() != old


def test_profile_change_waits_for_update_and_is_preserved(installed):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    engine, new = installed
    staged = threading.Event()
    release = threading.Event()
    profile_started = threading.Event()
    profile_done = threading.Event()
    def before_commit():
        staged.set()
        assert release.wait(3)
    def change_profile():
        profile_started.set()
        engine.set_game('10', 'Game', {'multiplier': 4})
        profile_done.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        updating = pool.submit(engine.install, new, 'new', before_commit)
        assert staged.wait(3)
        changing = pool.submit(change_profile)
        assert profile_started.wait(3)
        try:
            assert not profile_done.wait(0.05)
        finally:
            release.set()
        updating.result(timeout=3)
        changing.result(timeout=3)
    assert engine.status()['version'] == 'new'
    assert engine.status()['profiles']['10']['multiplier'] == 4


def test_parent_symlink_is_refused(installed):
    engine, new = installed
    directory = engine.local / 'lib'
    directory.rename(engine.local / 'real-lib')
    directory.symlink_to(engine.local / 'real-lib')
    before = snapshot(engine)
    with pytest.raises(lsfg.LsfgError, match='lsfg_conflict'):
        engine.install(new, 'new')
    assert snapshot(engine) == before


def test_adopting_foreign_config_over_owned_install_can_reinstall(installed):
    engine, new = installed
    profiles = engine.status()['profiles']
    engine.config_path.write_bytes(b'version = 2\n# External configuration\n')
    original = {path: content for path, content in snapshot(engine).items() if path != engine.manifest_path}
    engine.adopt_foreign()
    assert not engine.status()['installed']
    engine.install(new, 'new')
    assert engine.status()['profiles'] == profiles
    assert engine.status()['foreign_backup']
    engine.uninstall()
    engine.restore_foreign()
    assert {path: path.read_bytes() for path in original} == original


def test_update_preserves_existing_config_bytes(installed):
    engine, new = installed
    content = engine.config_path.read_bytes().replace(b'allow_fp16 = true', b'allow_fp16 = false')
    engine.config_path.write_bytes(content)
    engine.install(new, 'new')
    assert engine.config_path.read_bytes() == content
