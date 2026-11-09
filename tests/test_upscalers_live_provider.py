import json
import os

import pytest

from upscalers import diagnostics
from upscalers.service import UpscalerService


def make_service(tmp_path, log_text, engine='optiscaler'):
    target = tmp_path / 'game'
    target.mkdir()
    (target / 'OptiScaler.log').write_text(log_text)
    service = UpscalerService(str(tmp_path), str(tmp_path / 'state'), 'rdna2')
    install = {'engine': engine, 'target': str(target), 'build': 'fsr-4.1.1', 'installed_at': 1}
    service._game_state('292030')['install'] = install
    return service, install


def test_live_reports_observed_fsr_family_without_installed_version(tmp_path):
    service, install = make_service(tmp_path,
        'OptiScaler v0.9.4 loaded\nCreating new fsr31 upscaler\n'
        'amdxcffx64.dll loaded\nUpdateProviderEx result: 0\n'
        'Render Resolution: 960x540, Display Resolution 1920x1080\n')
    live = service.live('292030')
    assert live['provider_family'] == 'fsr'
    assert live['provider_name'] == 'FSR'
    assert live['provider_version'] is None
    assert live['provider_confidence'] == 'family_only'
    assert live['provider_source'] == 'optiscaler_log'
    assert live['resolution'] is None
    assert live['resolution_source'] == 'initialization_only'
    report = diagnostics.snapshot(install)
    assert report['applied']['build'] == 'fsr-4.1.1'
    assert report['observed']['initial_resolution'] == {'render': [960, 540], 'output': [1920, 1080]}
    assert 'resolution' not in report['observed']
    assert report['observed']['resolution_source'] == 'initialization_only'
    for key in ('provider_family', 'provider_name', 'provider_version', 'provider_source', 'provider_confidence'):
        assert report['observed'][key] == live[key]


@pytest.mark.parametrize('text', [
    'amdxcffx64.dll loaded\nUpdateProviderEx result: 0\n',
    'Creating new /home/private/provider upscaler\n',
    'OptiScaler v4.1.1 loaded\n',
])
def test_live_does_not_infer_provider_from_library_injector_or_unknown_token(tmp_path, text):
    service, _ = make_service(tmp_path, text)
    live = service.live('292030')
    assert live['provider_family'] is None
    assert live['provider_name'] is None
    assert live['provider_version'] is None
    assert live['provider_confidence'] == 'unknown'
    assert '/home/' not in json.dumps(live)


def test_live_stale_provider_is_unknown(tmp_path):
    service, install = make_service(tmp_path, 'Creating new fsr31 upscaler\n')
    install['verification_since'] = 100
    os.utime(tmp_path / 'game/OptiScaler.log', (1, 1))
    assert service.live('292030')['provider_family'] is None


@pytest.mark.parametrize('token,family,name', [
    ('FSR 3.X/4', 'fsr', 'FSR'), ('FSR 4.1.2 Lite', 'fsr', 'FSR'),
    ('DLSS', 'dlss', 'DLSS'), ('XeSS', 'xess', 'XeSS'),
])
def test_observed_family_never_promotes_route_version(tmp_path, token, family, name):
    service, _ = make_service(tmp_path, f'Creating new {token} upscaler\n')
    live = service.live('292030')
    assert live['provider_family'] == family
    assert live['provider_name'] == name
    assert live['provider_version'] is None


def test_latest_unrecognized_route_clears_observed_family(tmp_path):
    service, _ = make_service(tmp_path, 'Creating new fsr31 upscaler\nCreating new unknown upscaler\n')
    assert service.live('292030')['provider_family'] is None


def test_initial_dimensions_do_not_become_live_after_provider_switch(tmp_path):
    service, install = make_service(tmp_path,
        '[I] NVSDK_NGX_D3D12_CreateFeature Creating new fsr31 upscaler\n'
        '[I] IFeature::SetInitParameters Render Resolution: 960x540, Display Resolution 1920x1080, Quality: 1\n'
        '[I] init successful for XeSS, upscaler changed\n')
    entry = service._game_state('292030')
    entry['history'] = [{'build': install['build']}]
    live = service.live('292030')
    assert live['provider_family'] == 'xess'
    assert live['resolution'] is None
    assert live['resolution_source'] == 'initialization_only'
    verification = service.verify('292030')
    assert 'resolution' not in verification['facts']
    assert verification['facts']['initial_resolution']['render'] == [960, 540]
    assert entry['history'][-1]['facts']['initial_resolution']['render'] == [960, 540]
    assert 'resolution' not in entry['history'][-1]['facts']
    assert diagnostics.snapshot(install)['observed']['initial_resolution']['render'] == [960, 540]


def test_missing_or_stale_dimensions_have_no_initial_or_current_readback(tmp_path):
    service, install = make_service(tmp_path,
        'Render Resolution: 960x540, Display Resolution 1920x1080\n')
    install['verification_since'] = 100
    os.utime(tmp_path / 'game/OptiScaler.log', (1, 1))
    for remove in (False, True):
        if remove:
            (tmp_path / 'game/OptiScaler.log').unlink()
        live = service.live('292030')
        assert live['resolution'] is None
        assert live['resolution_source'] == 'unavailable'
        observed = diagnostics.snapshot(install)['observed']
        assert observed['resolution_source'] == 'unavailable'
        assert 'resolution' not in observed
        assert 'initial_resolution' not in observed


def test_upgrade_keeps_legacy_history_dimensions_only_as_initial(tmp_path):
    service, install = make_service(tmp_path, '')
    service._game_state('292030')['history'] = [{
        'build': install['build'], 'result': 'active',
        'facts': {'resolution': {'render': [960, 540], 'output': [1920, 1080]}, 'upscaler': 'XeSS'},
    }]
    service._save()
    reloaded = UpscalerService(str(tmp_path), str(tmp_path / 'state'), 'rdna2')
    facts = reloaded._game_state('292030')['history'][-1]['facts']
    assert 'resolution' not in facts
    assert facts['initial_resolution'] == {'render': [960, 540], 'output': [1920, 1080]}
    assert facts['resolution_source'] == 'initialization_only'
    assert facts['upscaler'] == 'XeSS'
    reloaded._save()
    assert reloaded._load() == reloaded.state


@pytest.mark.parametrize('events,expected', [
    ('ffxCreateContext_Dx12 context created: 1EE8\nCreateDLSSContext renderWidth: 960\nCreateXeSSContext\n', 'XeSS'),
    ('CreateXeSSContext\nffxCreateContext_Dx12 context created: 1EE8\nCreateDLSSContext renderWidth: 960\n', 'FSR3'),
    ('ffxCreateContext_Dx12 context created: 1EE8\nCreateFSR2Context\n', 'FSR2'),
])
def test_latest_explicit_input_wins_over_earlier_ffx_context(tmp_path, events, expected):
    service, _ = make_service(tmp_path, events)
    assert service.verify('292030')['facts']['input'] == expected
