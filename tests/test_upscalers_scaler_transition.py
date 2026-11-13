import copy
import json
from pathlib import Path

import pytest

from test_upscalers import APPID, _service, _write, dll_catalog, fake_catalog, proc, steam
from upscalers import games
from upscalers.service import UpscalerError


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_checkpoint_restores_exact_managed_files_ini_and_state(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test', 'quality': 'balanced'})
    install = service.state['games'][APPID]['install']
    target = Path(install['target'])
    _write(target / 'OptiScaler.ini', '[Custom]\nPrecise=0.375\n')
    install['edited'] = {'Custom.Precise': '0.375'}
    install['image_overrides'] = {'Sharpening.Sharpness': '0.375'}
    service.state['games'][APPID]['install']['args'] = ['-dx11']
    service.record_added_args(APPID, ['-dx11'], ['dxgi=n,b'], [])
    before = files(steam[1])
    entry = copy.deepcopy(service.state['games'][APPID])
    checkpoint = service.begin_scaler_transition(APPID)
    service.uninstall(APPID)
    result = service.finish_scaler_transition(APPID, checkpoint['token'], True)
    assert result['overrides'] == ['dxgi=n,b']
    assert files(steam[1]) == before
    assert service.state['games'][APPID] == entry
    assert service.begin_scaler_transition(APPID)['recovery'] is True
    service.finish_scaler_transition(APPID, checkpoint['token'], False)
    assert service.scaler_transitions.pending(APPID) is None


def test_new_dll_install_rollback_restores_original_bytes_and_cleanup(steam, dll_catalog, proc):
    service = _service(steam, dll_catalog, proc)
    before = files(steam[1])
    checkpoint = service.begin_scaler_transition(APPID)
    service.install(APPID, {'build': 'dll-test'})
    service.state['games'][APPID]['install']['added_args'] = ['-test']
    result = service.finish_scaler_transition(APPID, checkpoint['token'], True)
    assert result['removed_args'] == ['-test']
    assert result['overrides'] == []
    assert files(steam[1]) == before
    service.finish_scaler_transition(APPID, checkpoint['token'], False)


def test_commit_keeps_new_install(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    checkpoint = service.begin_scaler_transition(APPID)
    service.install(APPID, {'build': 'fsr-test'})
    after = files(steam[1])
    service.finish_scaler_transition(APPID, checkpoint['token'], False)
    assert files(steam[1]) == after
    assert service.state['games'][APPID]['install']['build'] == 'fsr-test'


def test_pending_checkpoint_survives_service_restart(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    before = files(steam[1])
    checkpoint = service.begin_scaler_transition(APPID)
    service.uninstall(APPID)
    restarted = _service(steam, fake_catalog, proc)
    recovery = restarted.begin_scaler_transition(APPID)
    assert recovery['recovery'] is True
    assert recovery['token'] == checkpoint['token']
    restarted.finish_scaler_transition(APPID, checkpoint['token'], True)
    assert files(steam[1]) == before


def test_rollback_over_an_external_change_keeps_it_and_releases_the_game(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    target = Path(service.state['games'][APPID]['install']['target'])
    checkpoint = service.begin_scaler_transition(APPID)
    service.uninstall(APPID)
    _write(target / 'dxgi.dll', b'external replacement')
    assert service.finish_scaler_transition(APPID, checkpoint['token'], True) is None
    assert (target / 'dxgi.dll').read_bytes() == b'external replacement'
    assert not service.scaler_transitions.pending(APPID)
    service.install(APPID, {'build': 'fsr-test'})


def test_changed_owned_binary_rejected_before_uninstall(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    target = Path(service.state['games'][APPID]['install']['target'])
    _write(target / 'dxgi.dll', b'not ours')
    with pytest.raises(UpscalerError, match='transition_conflict'):
        service.begin_scaler_transition(APPID)
    assert (target / 'dxgi.dll').read_bytes() == b'not ours'


@pytest.mark.parametrize('name', ['../../outside.dll', '/tmp/outside.dll'])
def test_manifest_path_traversal_rejected(steam, fake_catalog, proc, name):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    target = Path(service.state['games'][APPID]['install']['target'])
    path = target / games.MANIFEST_DIR / 'manifest.json'
    data = json.loads(path.read_text())
    data['files'][name] = None
    path.write_text(json.dumps(data))
    with pytest.raises(UpscalerError, match='transition_(unsafe_path|conflict)'):
        service.begin_scaler_transition(APPID)


def test_foreign_and_running_games_rejected(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    target = steam[1] / 'bin/x64_dx12'
    _write(target / 'OptiScaler.ini', b'foreign')
    with pytest.raises(UpscalerError, match='foreign'):
        service.begin_scaler_transition(APPID)
    (target / 'OptiScaler.ini').unlink()
    monkeypatch.setattr(games, 'running_under', lambda *args: True)
    with pytest.raises(UpscalerError, match='running'):
        service.begin_scaler_transition(APPID)


def test_new_optiscaler_rollback_preserves_unrelated_files(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    before = files(steam[1])
    checkpoint = service.begin_scaler_transition(APPID)
    service.install(APPID, {'build': 'fsr-test'})
    service.state['games'][APPID]['install']['args'] = ['-dx11']
    service.record_added_args(APPID, ['-dx11'], ['dxgi=n,b'], [])
    external = _write(steam[1] / 'unrelated-user-file', b'keep')
    result = service.finish_scaler_transition(APPID, checkpoint['token'], True)
    assert result['removed_overrides'] == ['dxgi=n,b']
    assert result['removed_args'] == ['-dx11']
    assert files(steam[1]) == {**before, 'unrelated-user-file': b'keep'}
    assert external.read_bytes() == b'keep'
    assert service.finish_scaler_transition(APPID, checkpoint['token'], True) == result
    service.finish_scaler_transition(APPID, checkpoint['token'], False)


def test_symlink_added_after_removal_is_not_followed(steam, fake_catalog, proc, tmp_path):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    target = Path(service.state['games'][APPID]['install']['target'])
    checkpoint = service.begin_scaler_transition(APPID)
    service.uninstall(APPID)
    external = _write(tmp_path / 'external', b'keep')
    (target / 'dxgi.dll').symlink_to(external)
    with pytest.raises(UpscalerError, match='transition_unsafe_path'):
        service.finish_scaler_transition(APPID, checkpoint['token'], True)
    assert external.read_bytes() == b'keep'


def test_partial_restore_failure_keeps_recoverable_checkpoint(steam, fake_catalog, proc, monkeypatch):
    from upscalers import scaler_transition
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    before = files(steam[1])
    checkpoint = service.begin_scaler_transition(APPID)
    service.uninstall(APPID)
    replace = scaler_transition.os.replace
    failed = False
    def fail_once(source, target):
        nonlocal failed
        if '.pdc-restore-' in str(source) and str(target).endswith('OptiScaler.ini') and not failed:
            failed = True
            raise OSError('disk failure')
        return replace(source, target)
    monkeypatch.setattr(scaler_transition.os, 'replace', fail_once)
    with pytest.raises(UpscalerError, match='transition_conflict'):
        service.finish_scaler_transition(APPID, checkpoint['token'], True)
    assert service.scaler_transitions.pending(APPID)
    service.finish_scaler_transition(APPID, checkpoint['token'], True)
    assert files(steam[1]) == before
    service.finish_scaler_transition(APPID, checkpoint['token'], False)


def test_unsupported_install_is_not_touched(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service._game_state(APPID)['install'] = {'engine': 'proton', 'target': str(steam[1])}
    with pytest.raises(UpscalerError, match='transition_unsupported'):
        service.begin_scaler_transition(APPID)
    assert service.state['games'][APPID]['install']['engine'] == 'proton'


def test_recovery_preserves_original_mako_profile_and_waits_for_job(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    profile = {'enabled': True, 'scaling_enabled': True, 'multiplier': 3, 'scaling_sharpness': 0.35}
    monkeypatch.setattr(service, 'mako_status', lambda appid: {'profiles': {appid: profile}})
    checkpoint = service.begin_scaler_transition(APPID)
    profile['enabled'] = False
    service._job = {'state': 'running'}
    with pytest.raises(UpscalerError, match='busy'):
        service.begin_scaler_transition(APPID)
    with pytest.raises(UpscalerError, match='busy'):
        service.finish_scaler_transition(APPID, checkpoint['token'], True)
    restarted = _service(steam, fake_catalog, proc)
    recovery = restarted.begin_scaler_transition(APPID)
    assert recovery['previous_mako']['enabled'] is True
    assert recovery['previous_mako']['multiplier'] == 3
    assert recovery['recovery'] is True


def test_status_exposes_pending_recovery_after_restart(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    checkpoint = service.begin_scaler_transition(APPID)
    restarted = _service(steam, fake_catalog, proc)
    assert restarted.mako_status(APPID)['scaler_transition_pending'] is True
    restarted.finish_scaler_transition(APPID, checkpoint['token'], True)
    assert restarted.mako_status(APPID)['scaler_transition_pending'] is True
    restarted.finish_scaler_transition(APPID, checkpoint['token'], False)
    assert restarted.mako_status(APPID)['scaler_transition_pending'] is False
