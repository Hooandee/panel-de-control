import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from upscalers import mako


def write(path, content=b'x'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(mako.platform, 'machine', lambda: 'x86_64')
    home = tmp_path / 'home'
    library = home / '.steam/steam'
    dll = write(library / 'steamapps/common/Lossless Scaling/Lossless.dll')
    monkeypatch.setattr(mako.games, 'library_paths', lambda home: [library])
    manager = mako.Mako(str(home), tmp_path / 'state')
    archive = tmp_path / 'mako.tar.xz'
    with tarfile.open(archive, 'w:xz') as handle:
        for name in mako.PAYLOAD:
            content = b'#!/bin/sh\nexit 0\n' if name.startswith('bin/') else b'layer'
            info = tarfile.TarInfo('./' + name)
            info.size = len(content)
            handle.addfile(info, io.BytesIO(content))
    monkeypatch.setattr(mako, 'ASSET', SimpleNamespace(sha256=hashlib.sha256(archive.read_bytes()).hexdigest()))
    cache = SimpleNamespace(ensure=lambda *args: archive)
    calls = []
    def inspect(args, **kwargs):
        calls.append(args)
        kwargs['stdout'].write(b'{"schema_version":1,"compatible":true}')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(mako.subprocess, 'run', inspect)
    return manager, cache, dll, calls


def test_install_private_and_apply_preserve_foreign_configuration(setup):
    manager, cache, dll, calls = setup
    foreign = write(manager.home / '.config/mako-render/conf.toml', b'foreign config')
    assert manager.status()['ready'] is False
    manager.install(cache)
    assert manager.status()['installed'] is True
    assert manager.status()['ready'] is False
    result = manager.set_game('123', 'Private game name', {'mode': 'adaptive', 'target_fps': 90, 'max_multiplier': 4})
    assert calls[0][1:] == ['inspect-dll', '--dll', str(dll), '--lsfg']
    config = Path(result['env']['MAKO_CONFIG']).read_text()
    assert 'adaptive = true' in config and 'target_fps = 90' in config
    assert 'scaling_enabled = false' in config and 'scaling_sharpness' not in config
    assert result['env']['MAKO_PROFILE'] == 'pdc-123'
    assert result['wrappers'] == [str(manager.prefix / 'bin/mako-launch')]
    assert foreign.read_bytes() == b'foreign config'
    assert manager.status()['ready'] is True
    assert manager.status()['profiles']['123']['enabled'] is True
    assert not (manager.home / '.local/share/vulkan/implicit_layer.d').exists()


@pytest.mark.parametrize('config', [{'multiplier': 6}, {'target_fps': 241}, {'max_multiplier': 1}, {'performance': 1}, {'flow': 'random'}, {'mode': 'wrong'}, {'enabled': 'yes'}, {'sharpness': .8}])
def test_reject_bad_config_before_changes(setup, config):
    manager, cache, _, _ = setup
    manager.install(cache)
    with pytest.raises(mako.MakoError, match='mako_options'):
        manager.set_game('123', 'game', config)
    assert manager.status()['profiles'] == {}


def test_inspection_failure_keeps_previous_and_retry_works(setup, monkeypatch):
    manager, cache, _, _ = setup
    manager.install(cache)
    result = manager.set_game('123', 'game', {})
    path = Path(result['env']['MAKO_CONFIG'])
    before = path.read_bytes()
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('private path', 10)
    monkeypatch.setattr(mako.subprocess, 'run', timeout)
    with pytest.raises(mako.MakoError, match='mako_inspection_timeout'):
        manager.set_game('123', 'game', {'multiplier': 3})
    assert path.read_bytes() == before
    assert manager.status()['profiles']['123']['multiplier'] == 2
    assert 'private path' not in json.dumps(manager.report())


def test_remove_only_owned_config_and_reject_external_changes(setup):
    manager, cache, _, _ = setup
    manager.install(cache)
    result = manager.set_game('123', 'game', {})
    path = Path(result['env']['MAKO_CONFIG'])
    path.write_text('foreign edit')
    with pytest.raises(mako.MakoError, match='mako_conflict'):
        manager.set_game('123', 'game', None)
    assert path.read_text() == 'foreign edit'


def test_remove_and_reapply_does_not_require_dll(setup):
    manager, cache, dll, _ = setup
    manager.install(cache)
    result = manager.set_game('123', 'game', {})
    dll.unlink()
    assert manager.set_game('123', 'game', None)['env'] == {}
    assert 'frame_generation_enabled = false' in Path(result['env']['MAKO_CONFIG']).read_text()
    assert manager.status()['profiles'] == {}


def test_archive_traversal_and_hash_failure_never_install(setup, monkeypatch, tmp_path):
    manager, cache, _, _ = setup
    path = tmp_path / 'evil.tar.xz'
    with tarfile.open(path, 'w:xz') as handle:
        info = tarfile.TarInfo('../escape')
        info.size = 1
        handle.addfile(info, io.BytesIO(b'x'))
    monkeypatch.setattr(mako, 'ASSET', SimpleNamespace(sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    with pytest.raises(mako.MakoError, match='mako_archive'):
        manager.install(SimpleNamespace(ensure=lambda *args: path))
    assert not manager.prefix.exists()
    monkeypatch.setattr(mako, 'ASSET', SimpleNamespace(sha256='0' * 64))
    with pytest.raises(mako.MakoError, match='mako_checksum'):
        manager.install(cache)


def test_runtime_is_observed_bounded_and_reports_no_paths(setup, monkeypatch):
    manager, cache, _, _ = setup
    manager.install(cache)
    result = manager.set_game('123', 'private title', {})
    path = Path(result['env']['MAKO_CONFIG']).parent / 'runtime-state/42-123-frame-generation-1.json'
    data = {'schema_version': 5, 'pid': 42, 'process_start_ticks': 123, 'role': 'frame-generation',
            'updated_unix_ms': 1000000, 'phase': 'applied', 'reason': '/home/private/game',
            'frame_generation_active': True, 'requested': {'name': 'pdc-123', 'multiplier': 3},
            'applied': {'name': 'pdc-123', 'multiplier': 2}, 'pending': {'process_restart': True}, 'error': '/private/error'}
    write(path, json.dumps(data).encode())
    monkeypatch.setattr(mako.time, 'time', lambda: 1000)
    monkeypatch.setattr(manager, '_process_matches', lambda pid, ticks: True)
    monkeypatch.setattr(manager, '_runtime_locked', lambda path: True)
    runtime = manager.runtime('123')
    assert runtime['observed'] is True and runtime['active'] is True
    assert runtime['applied']['multiplier'] == 2
    assert runtime['pending']['process_restart'] is True
    report = json.dumps(manager.report())
    assert '/home/' not in report and '/private/' not in report and 'private title' not in report
    monkeypatch.setattr(manager, '_process_matches', lambda pid, ticks: False)
    assert manager.runtime('123')['observed'] is False


def test_dll_replacement_invalidates_compatibility(setup):
    manager, cache, dll, _ = setup
    manager.install(cache)
    manager.set_game('123', 'game', {})
    assert manager.status()['ready'] is True
    dll.write_bytes(b'new unknown dll')
    assert manager.status()['ready'] is False


def test_failed_write_restores_both_files_and_profile(setup, monkeypatch):
    manager, cache, _, _ = setup
    manager.install(cache)
    result = manager.set_game('123', 'game', {})
    path = Path(result['env']['MAKO_CONFIG'])
    before = path.read_bytes()
    original = manager._write
    def failing(path, content):
        if path.name == 'launcher.conf':
            raise OSError('private failure')
        return original(path, content)
    monkeypatch.setattr(manager, '_write', failing)
    with pytest.raises(mako.MakoError, match='mako_write_failed'):
        manager.set_game('123', 'game', {'multiplier': 4})
    assert path.read_bytes() == before
    assert manager.status()['profiles']['123']['multiplier'] == 2
    monkeypatch.setattr(manager, '_write', original)
    assert manager.set_game('123', 'game', {'multiplier': 4})['profile']['multiplier'] == 4


def test_report_rejects_corrupt_values_and_unrecognized_profiles(setup):
    manager, _, _, _ = setup
    manager._save({'profiles': {'123': {'flow': '/private/name', 'multiplier': '/private/secret'},
                               '../../private': {'enabled': True}},
                   'events': [{'at': '/private/time', 'action': '/private/path', 'appid': '/private/name', 'code': '/private/secret'}]})
    assert '/private/' not in json.dumps(manager.report())


def test_unsupported_arch_and_incompatible_dll_are_explicit(setup, monkeypatch):
    manager, cache, _, _ = setup
    monkeypatch.setattr(mako.platform, 'machine', lambda: 'aarch64')
    assert manager.status()['reason'] == 'mako_arch'
    with pytest.raises(mako.MakoError, match='mako_arch'):
        manager.install(cache)
    monkeypatch.setattr(mako.platform, 'machine', lambda: 'x86_64')
    manager.install(cache)
    def incompatible(args, **kwargs):
        kwargs['stdout'].write(b'{"compatible":false}')
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(mako.subprocess, 'run', incompatible)
    with pytest.raises(mako.MakoError, match='mako_dll_incompatible'):
        manager.set_game('123', 'game', {})
    assert manager.status()['profiles'] == {}


def test_config_cli_rejection_leaves_previous_profile(setup, monkeypatch):
    manager, cache, _, _ = setup
    manager.install(cache)
    result = manager.set_game('123', 'game', {})
    before = Path(result['env']['MAKO_CONFIG']).read_bytes()
    def inspect(args, **kwargs):
        kwargs['stdout'].write(b'{"compatible":true}')
        return SimpleNamespace(returncode=1 if args[1] == 'validate' else 0)
    monkeypatch.setattr(mako.subprocess, 'run', inspect)
    with pytest.raises(mako.MakoError, match='mako_config_invalid'):
        manager.set_game('123', 'game', {'multiplier': 5})
    assert Path(result['env']['MAKO_CONFIG']).read_bytes() == before


def test_install_state_failure_rolls_back_and_allows_retry(setup, monkeypatch):
    manager, cache, _, _ = setup
    original = manager._save
    def fail(state):
        raise OSError('disk error private')
    monkeypatch.setattr(manager, '_save', fail)
    with pytest.raises(mako.MakoError, match='mako_write_failed'):
        manager.install(cache)
    assert not manager.prefix.exists()
    monkeypatch.setattr(manager, '_save', original)
    assert manager.install(cache)['installed'] is True


def test_runtime_resolves_steam_pid_namespace(setup, monkeypatch, tmp_path):
    manager, _, _, _ = setup
    proc = tmp_path / 'proc'
    host = proc / '25985'
    stat = '25985 (game name) ' + ' '.join(['S'] + ['0'] * 18 + ['898084'])
    write(host / 'stat', stat.encode())
    write(host / 'status', b'Name:\tgame\nNSpid:\t25985\t3714\n')
    original_read = Path.read_text
    original_scandir = mako.os.scandir
    monkeypatch.setattr(Path, 'read_text', lambda path, *a, **kw: original_read(
        proc / path.relative_to('/proc') if path.is_relative_to('/proc') else path, *a, **kw))
    monkeypatch.setattr(mako.os, 'scandir', lambda path: original_scandir(proc if str(path) == '/proc' else path))
    data = {'schema_version': 5, 'pid': 3714, 'process_start_ticks': 898084,
            'role': 'frame-generation', 'updated_unix_ms': 1000000,
            'frame_generation_active': True, 'requested': {'name': 'pdc-123'}}
    path = manager.config_root / '123/runtime-state/state.json'
    write(path, json.dumps(data).encode())
    monkeypatch.setattr(manager, '_runtime_locked', lambda path: True)
    runtime = manager.runtime('123')
    assert runtime['observed'] is True
    assert runtime['active'] is True
    write(host / 'stat', stat.replace('898084', '898085').encode())
    rejected = manager.runtime('123')
    assert rejected['observed'] is False
    assert rejected['rejections'] == {'process_identity': 1}


@pytest.fixture
def process_tree(tmp_path, monkeypatch):
    proc = tmp_path / 'proc'
    proc.mkdir()
    original_read = Path.read_text
    original_scandir = mako.os.scandir
    scans = []
    monkeypatch.setattr(Path, 'read_text', lambda path, *a, **kw: original_read(
        proc / path.relative_to('/proc') if path.is_relative_to('/proc') else path, *a, **kw))
    def scandir(path):
        if str(path) == '/proc':
            scans.append(True)
            return original_scandir(proc)
        return original_scandir(path)
    monkeypatch.setattr(mako.os, 'scandir', scandir)
    def process(host, nested, ticks):
        write(proc / str(host) / 'stat', (f'{host} (game) ' + ' '.join(['S'] + ['0'] * 18 + [str(ticks)])).encode())
        write(proc / str(host) / 'status', f'NSpid:\t{host}\t{nested}\n'.encode())
    return proc, process, scans


def test_process_namespace_cache_revalidates_and_recovers(setup, process_tree, monkeypatch):
    manager, _, _, _ = setup
    proc, process, scans = process_tree
    clock = [100.0]
    monkeypatch.setattr(mako.time, 'monotonic', lambda: clock[0])
    process(25985, 3714, 898084)
    assert manager._process_matches(3714, 898084)
    assert manager._process_matches(3714, 898084)
    assert not manager._process_matches(99, 898084)
    assert len(scans) == 1
    (proc / '25985/status').unlink()
    assert not manager._process_matches(3714, 898084)
    process(25986, 3714, 898084)
    clock[0] += 2
    assert manager._process_matches(3714, 898084)
    assert len(scans) == 2
    process(25987, 3714, 898084)
    clock[0] += 2
    assert not manager._process_matches(3714, 898084)


def test_direct_process_match_never_scans_namespace(setup, process_tree):
    manager, _, _, _ = setup
    _, process, scans = process_tree
    process(3714, 1, 898084)
    assert manager._process_matches(3714, 898084)
    assert scans == []
    for pid, ticks in ((True, 898084), (3714, True), (-1, 898084), (3714, -1)):
        assert not manager._process_matches(pid, ticks)


@pytest.mark.parametrize('change,locked,reason', [
    ({'schema_version': 4}, True, 'schema_or_role'),
    ({'updated_unix_ms': float('nan')}, True, 'timestamp'),
    ({'requested': {'name': 'pdc-456'}}, True, 'profile'),
    ({}, False, 'writer_unlocked'),
])
def test_runtime_rejections_keep_identity_protections(setup, monkeypatch, change, locked, reason):
    manager, _, _, _ = setup
    data = {'schema_version': 5, 'pid': 3714, 'process_start_ticks': 898084,
            'role': 'frame-generation', 'updated_unix_ms': 1000000,
            'requested': {'name': 'pdc-123'}} | change
    write(manager.config_root / '123/runtime-state/state.json', json.dumps(data).encode())
    monkeypatch.setattr(manager, '_runtime_locked', lambda path: locked)
    def unexpected_lookup(*args):
        pytest.fail('Rejected state must not trigger a process scan')
    monkeypatch.setattr(manager, '_process_matches', unexpected_lookup)
    assert manager.runtime('123') == {'observed': False, 'active': None, 'rejections': {reason: 1}}


def test_namespace_scan_limit_fails_closed(setup, monkeypatch):
    manager, _, _, _ = setup
    monkeypatch.setattr(manager, '_process_started', lambda pid, ticks: pid != 3714)
    monkeypatch.setattr(manager, '_namespace_pids', lambda pid: [3714] if pid == 10000 else [])
    class Entries:
        def __enter__(self):
            return iter(SimpleNamespace(name=str(pid)) for pid in range(10000, 14097))
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(mako.os, 'scandir', lambda path: Entries())
    assert not manager._process_matches(3714, 898084)
