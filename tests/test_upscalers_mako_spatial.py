import json
from pathlib import Path

import pytest

from test_upscalers_mako import setup, write
from test_upscalers_mako_update import release
from upscalers import mako


def test_spatial_without_dll_and_partial_coexistence(setup):
    manager, cache, dll, calls = setup
    manager.install(cache)
    dll.unlink()
    spatial = manager.set_game('123', 'game', {'enabled': False, 'scaling_enabled': True})
    path = Path(spatial['env']['MAKO_CONFIG'])
    assert 'scaling_method = "mako"' in path.read_text()
    assert 'scaling_supersampling = false' in path.read_text()
    assert 'frame_generation_provisioned = false' in path.read_text()
    assert not any(call[1] == 'inspect-dll' for call in calls)
    assert manager.status()['spatial_ready'] is True
    assert manager.status()['ready'] is False
    with pytest.raises(mako.MakoError, match='mako_dll_missing'):
        manager.set_game('123', 'game', {'enabled': True})
    assert manager.status()['profiles']['123']['enabled'] is False
    write(dll)
    combined = manager.set_game('123', 'game', {'enabled': True, 'multiplier': 3})
    assert combined['profile']['scaling_enabled'] is True
    assert combined['profile']['scaling_factor'] == 1.5
    fg = manager.set_game('123', 'game', {'scaling_enabled': False})
    assert fg['profile']['enabled'] is True and fg['profile']['multiplier'] == 3
    assert manager.set_game('123', 'game', {'enabled': False})['profile'] is None
    assert 'scaling_enabled = false' in path.read_text()


def test_none_disables_both_and_legacy_defaults_to_fg(setup):
    manager, cache, _, _ = setup
    manager.install(cache)
    legacy = manager.set_game('123', 'game', {})
    assert legacy['profile']['enabled'] is True
    assert legacy['profile']['scaling_enabled'] is False
    combined = manager.set_game('123', 'game', {'scaling_enabled': True})
    path = Path(combined['env']['MAKO_CONFIG'])
    assert manager.set_game('123', 'game', None)['wrappers'] == []
    assert 'scaling_enabled = false' in path.read_text()
    assert 'frame_generation_enabled = false' in path.read_text()


@pytest.mark.parametrize('key,value', [
    ('scaling_enabled', 1), ('scaling_factor', True), ('scaling_factor', .99),
    ('scaling_factor', 2.01), ('scaling_factor', float('nan')),
    ('scaling_sharpness', -.01), ('scaling_sharpness', 1.01),
    ('scaling_sharpness', float('inf')), ('scaling_sharpness', '0.8'),
    ('scaling_method', 'ls1'), ('supersampling', True),
])
def test_spatial_invalid_options_preserve_profile(setup, key, value):
    manager, cache, _, _ = setup
    manager.install(cache)
    manager.set_game('123', 'game', {'enabled': False, 'scaling_enabled': True})
    before = manager.status()['profiles']
    with pytest.raises(mako.MakoError, match='mako_options'):
        manager.set_game('123', 'game', {key: value})
    assert manager.status()['profiles'] == before


@pytest.mark.parametrize('factor,sharpness', [(1, 0), (2, 1)])
def test_spatial_boundaries_and_upgrade_without_dll(setup, factor, sharpness):
    manager, cache, dll, calls = setup
    manager.install(cache)
    dll.unlink()
    launch = manager.set_game('123', 'game', {'enabled': False, 'scaling_enabled': True,
                                             'scaling_factor': factor, 'scaling_sharpness': sharpness})
    path = Path(launch['env']['MAKO_CONFIG'])
    before = path.read_bytes()
    next_cache, asset = release(manager)
    result = manager.install(next_cache, asset=asset, version='4.6.1')
    assert path.read_bytes() == before
    assert result['profiles']['123']['scaling_factor'] == factor
    assert result['profiles']['123']['scaling_sharpness'] == sharpness
    assert not any(call[1] == 'inspect-dll' for call in calls)


@pytest.mark.parametrize('role', ['frame-generation', 'spatial-scaling'])
def test_runtime_observes_spatial_without_claiming_fg(setup, monkeypatch, role):
    manager, cache, _, _ = setup
    manager.install(cache)
    launch = manager.set_game('123', 'game', {'enabled': False, 'scaling_enabled': True})
    path = Path(launch['env']['MAKO_CONFIG']).parent / 'runtime-state/42.json'
    write(path, json.dumps({'schema_version': 5, 'pid': 42, 'process_start_ticks': 123,
                           'role': role, 'updated_unix_ms': 1000000,
                           'frame_generation_active': False, 'spatial_scaling': {'active': True},
                           'requested': {'name': 'pdc-123'},
                           'applied': {'scaling_factor': 1.5, 'scaling_sharpness': .8}}).encode())
    monkeypatch.setattr(mako.time, 'time', lambda: 1000)
    monkeypatch.setattr(manager, '_process_matches', lambda *args: True)
    monkeypatch.setattr(manager, '_runtime_locked', lambda *args: True)
    result = manager.runtime('123')
    assert result['observed'] is True and result['active'] is False
    assert result['scaling_active'] is True and result['role'] == role
    assert result['applied']['scaling_sharpness'] == .8


@pytest.mark.parametrize('requested,active,expected', [
    ('mako', 'native', {'requested_method': 'mako', 'active_method': 'native'}),
    ('ls1', 'ls1-performance', {'requested_method': 'ls1', 'active_method': 'ls1-performance'}),
    ('/home/private/game', {'private': 'value'}, {}),
])
def test_runtime_spatial_methods_are_observed_and_allowlisted(setup, monkeypatch, requested, active, expected):
    manager, _, _, _ = setup
    path = manager.config_root / '123/runtime-state/42.json'
    write(path, json.dumps({'schema_version': 5, 'pid': 42, 'process_start_ticks': 123,
                           'role': 'frame-generation', 'updated_unix_ms': 1000000,
                           'frame_generation_active': False,
                           'spatial_scaling': {'active': True, 'requested_method': requested,
                                               'active_method': active, 'fallback_reason': '/home/private/reason'},
                           'requested': {'name': 'pdc-123'}}).encode())
    monkeypatch.setattr(mako.time, 'time', lambda: 1000)
    monkeypatch.setattr(manager, '_process_matches', lambda *args: True)
    monkeypatch.setattr(manager, '_runtime_locked', lambda *args: True)
    result = manager.runtime('123')
    assert result['spatial_methods'] == expected
    assert result['active'] is False and result['scaling_active'] is True
    assert 'private' not in json.dumps(result)


@pytest.mark.parametrize('reason,expected', [
    ('gamescope-presentation-target-no-headroom', 'gamescope-presentation-target-no-headroom'),
    ('/home/private/game', None),
    ({'private': 'value'}, None),
    (None, None),
])
def test_runtime_scaling_reason_is_allowlisted(setup, monkeypatch, reason, expected):
    manager, _, _, _ = setup
    path = manager.config_root / '123/runtime-state/42.json'
    write(path, json.dumps({'schema_version': 5, 'pid': 42, 'process_start_ticks': 123,
                           'role': 'frame-generation', 'updated_unix_ms': 1000000,
                           'spatial_scaling': {'active': False, 'inactive_reason': reason},
                           'requested': {'name': 'pdc-123'}}).encode())
    monkeypatch.setattr(mako.time, 'time', lambda: 1000)
    monkeypatch.setattr(manager, '_process_matches', lambda *args: True)
    monkeypatch.setattr(manager, '_runtime_locked', lambda *args: True)
    result = manager.runtime('123')
    assert result['scaling_inactive_reason'] == expected
    assert 'private' not in json.dumps(result)
    monkeypatch.setattr(manager, '_process_matches', lambda *args: False)
    assert manager.runtime('123')['observed'] is False

@pytest.mark.parametrize('width', [1280, 0, -1, True, 1.5, '1280', None, 32769])
def test_runtime_projects_only_complete_valid_observed_dimensions(setup, monkeypatch, width):
    manager, _, _, _ = setup
    path = manager.config_root / '123/runtime-state/42.json'
    write(path, json.dumps({'schema_version': 5, 'pid': 42, 'process_start_ticks': 123,
                           'role': 'frame-generation', 'updated_unix_ms': 1000000,
                           'frame_generation_active': False,
                           'spatial_scaling': {'active': True, 'active_method': 'mako',
                               'source_width': width, 'source_height': 720,
                               'presentation_width': 1920, 'presentation_height': 1080},
                           'requested': {'name': 'pdc-123'}}).encode())
    monkeypatch.setattr(mako.time, 'time', lambda: 1000)
    monkeypatch.setattr(manager, '_process_matches', lambda *args: True)
    monkeypatch.setattr(manager, '_runtime_locked', lambda *args: True)
    result = manager.runtime('123')
    assert result['active'] is False and result['scaling_active'] is True
    assert result['spatial_resolution'] == ({'render': [1280, 720], 'output': [1920, 1080]}
                                            if width == 1280 else None)
