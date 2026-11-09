import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from upscalers import engine_updates, lsfg
from upscalers.service import UpscalerService


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(engine_updates, 'fetch', Mock(side_effect=OSError('offline')))


def release(number, **fields):
    filename = f'MAKO-Renderer-v{number}-linux.tar.xz'
    return {'tag_name': f'render-v{number}', 'assets': [{
        'name': filename, 'size': 1024, 'digest': 'sha256:' + 'a' * 64,
        'browser_download_url': f'https://github.com/eugeniosegala/MAKO/releases/download/render-v{number}/{filename}',
    }], **fields}


def test_mako_discovers_latest_stable_same_major(monkeypatch):
    releases = [release('4.6.1'), release('4.8.0'), release('4.9.0', prerelease=True),
                release('4.10.0', draft=True), release('5.0.0'), release('4.6.0')]
    monkeypatch.setattr(engine_updates, 'fetch', lambda *_: json.dumps(releases).encode())
    assert engine_updates.discover('mako', '4.6.0')['version'] == '4.8.0'
    assert engine_updates.discover('mako', '4.8.0') is None


def test_mako_rejects_unverified_or_wrong_origin_assets(monkeypatch):
    no_digest = release('4.7.0')
    no_digest['assets'][0]['digest'] = None
    other_origin = release('4.8.0')
    other_origin['assets'][0]['browser_download_url'] = 'https://example.invalid/mako.tar.xz'
    monkeypatch.setattr(engine_updates, 'fetch', lambda *_: json.dumps([no_digest, other_origin]).encode())
    assert engine_updates.discover('mako', '4.6.0') is None


def test_lsfg_discovery_ignores_prerelease_and_other_major(monkeypatch):
    html = b'<a href="lsfg-vk-2.0.1.tar.xz"><a href="lsfg-vk-2.1.0.tar.xz"><a href="lsfg-vk-3.0.0.tar.xz"><a href="lsfg-vk-2.2.0-rc1.tar.xz">'
    monkeypatch.setattr(engine_updates, 'fetch', lambda *_: html)
    assert engine_updates.discover('lsfg', 'lsfg-vk-2.0.0')['version'] == '2.1.0'
    assert engine_updates.discover('lsfg', '2.1.0') is None


@pytest.fixture
def service(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    proc = tmp_path / 'proc'
    process = proc / '100'
    process.mkdir(parents=True)
    (process / 'environ').write_bytes(b'HOME=/home/test\0')
    (process / 'cmdline').write_bytes(b'/usr/bin/steam\0')
    result = UpscalerService(str(home), str(tmp_path / 'state'), 'rdna2', proc=str(proc))
    old = tmp_path / 'old'
    for name in lsfg.LAYER_FILES:
        path = old / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'old layer')
    result.lsfg.install(old, 'lsfg-vk-2.0.0')
    result.lsfg.set_game('42', 'Game', {'multiplier': 3})
    return result


def snapshot(service):
    engine = service.lsfg
    return {path: path.read_bytes() for path in [engine.manifest_path, engine.config_path,
            *(engine.local / name for name in lsfg.LAYER_FILES)]}


def candidate(monkeypatch):
    value = {'version': '2.0.1', 'url': 'https://builds.lsfg-vk.dev/lsfg-vk-2.0.1.tar.xz'}
    monkeypatch.setattr(engine_updates, 'discover', Mock(return_value=value))
    return value


def archive():
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:xz') as handle:
        for name in lsfg.LAYER_FILES:
            content = b'new ' + name.encode()
            info = tarfile.TarInfo(name)
            info.size = len(content)
            handle.addfile(info, io.BytesIO(content))
    return output.getvalue()


def test_check_available_does_not_download_or_change_install(service, monkeypatch):
    candidate(monkeypatch)
    before = snapshot(service)
    assert service.refresh_engine('lsfg') == {'state': 'available', 'version': '2.0.0', 'available': '2.0.1'}
    engine_updates.fetch.assert_not_called()
    assert snapshot(service) == before


def test_current_result_is_cached(service, monkeypatch):
    discovery = Mock(return_value=None)
    monkeypatch.setattr(engine_updates, 'discover', discovery)
    assert service.refresh_engine('lsfg', True) == {'state': 'current', 'version': '2.0.0'}
    service.refresh_engine('lsfg')
    discovery.assert_called_once()


def test_offline_check_retains_installation(service):
    before = snapshot(service)
    assert service.refresh_engine('lsfg', True)['state'] == 'failed'
    assert snapshot(service) == before


def test_failed_download_retains_version_and_profiles(service, monkeypatch):
    candidate(monkeypatch)
    before = snapshot(service)
    result = service.refresh_engine('lsfg', True)
    assert result['state'] == 'failed' and result['version'] == '2.0.0'
    assert snapshot(service) == before


def test_running_game_defers_before_download(service, monkeypatch):
    candidate(monkeypatch)
    service.engine_game_running = lambda: True
    before = snapshot(service)
    assert service.refresh_engine('lsfg', True)['state'] == 'deferred'
    engine_updates.fetch.assert_not_called()
    assert snapshot(service) == before


def test_game_starting_during_download_defers_before_publish(service, monkeypatch):
    candidate(monkeypatch)
    before = snapshot(service)
    def download(*_):
        (Path(service.proc) / '100/environ').write_bytes(b'SteamAppId=42\0')
        return archive()
    monkeypatch.setattr(engine_updates, 'fetch', download)
    assert service.refresh_engine('lsfg', True)['state'] == 'deferred'
    assert snapshot(service) == before


def test_service_updates_lsfg_and_preserves_profile(service, monkeypatch):
    candidate(monkeypatch)
    monkeypatch.setattr(engine_updates, 'fetch', lambda *_: archive())
    assert service.refresh_engine('lsfg', True) == {'state': 'updated', 'version': '2.0.1'}
    assert service.lsfg.status()['version'] == 'lsfg-vk-2.0.1'
    assert service.lsfg.status()['profiles']['42']['multiplier'] == 3


@pytest.mark.parametrize('engine,number', [('lsfg', 'lsfg-vk-2.1.0'), ('mako', '4.8.0')])
def test_install_rpc_does_not_downgrade_installed_engine(service, monkeypatch, engine, number):
    motor = getattr(service, engine)
    monkeypatch.setattr(motor, 'status', lambda: {'installed': True, 'version': number})
    install = Mock(side_effect=AssertionError('must not replace installed engine'))
    monkeypatch.setattr(motor, 'install', install)
    assert getattr(service, engine + '_install')()['version'] == number
    install.assert_not_called()


@pytest.mark.parametrize('environment', [b'SteamAppId=42\0', b'SteamGameId=999999999999\0'])
def test_idle_guard_detects_steam_game(service, environment):
    (Path(service.proc) / '100/environ').write_bytes(environment)
    with pytest.raises(engine_updates.UpdateError, match='engine_deferred'):
        service._ensure_engine_idle()


def test_idle_guard_detects_known_native_game(service, monkeypatch):
    root = Path(service.home) / 'games/native'
    service.state['games']['native'] = {}
    monkeypatch.setattr(service, '_find', lambda _: SimpleNamespace(root=root))
    (Path(service.proc) / '100/cmdline').write_bytes(str(root / 'game').encode())
    with pytest.raises(engine_updates.UpdateError, match='engine_deferred'):
        service._ensure_engine_idle()


def test_idle_guard_detects_wine_game(service):
    (Path(service.proc) / '100/cmdline').write_bytes(b'wine\0Game.exe\0')
    with pytest.raises(engine_updates.UpdateError, match='engine_deferred'):
        service._ensure_engine_idle()


def test_idle_guard_refuses_unreadable_process_environment(service, monkeypatch):
    read = Path.read_bytes
    def denied(path):
        if path == Path(service.proc) / '100/environ':
            raise PermissionError('denied')
        return read(path)
    monkeypatch.setattr(Path, 'read_bytes', denied)
    with pytest.raises(engine_updates.UpdateError, match='engine_deferred'):
        service._ensure_engine_idle()


def test_idle_guard_refuses_unavailable_proc(service):
    service.proc += '-missing'
    with pytest.raises(engine_updates.UpdateError, match='engine_deferred'):
        service._ensure_engine_idle()


def test_idle_guard_accepts_observed_idle_session(service):
    service._ensure_engine_idle()
