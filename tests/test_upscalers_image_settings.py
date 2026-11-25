import dataclasses
from pathlib import Path

import pytest

from upscalers import games, image_settings, ini
from upscalers.service import UpscalerError, UpscalerService

TEXT = '; HelixSR Scaler\r\n[HelixSR]\r\nInt8=auto\r\n[Sharpness]\r\nShader=da\r\nOverrideSharpness=auto\r\nSharpness=auto\r\n[CAS]\r\nEnabled=auto\r\n[Other]\r\nUntouched=yes\r\n'


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / 'game'
    root.mkdir()
    path = root / 'OptiScaler.ini'
    path.write_bytes(TEXT.encode())
    (root / 'game.exe').write_bytes(b'MZ')
    provider = root / 'HelixSR/helixsr.dll'
    provider.parent.mkdir()
    provider.write_bytes(b'provider')
    (root / 'OptiScaler.log').write_text('FFX upscaler: HLX DLSS (version name test)')
    service = UpscalerService(str(tmp_path), str(tmp_path / 'state'), 'rdna2', proc=str(tmp_path / 'proc'))
    installed = games.Installed('1', 'Game', root, 4, 'game.exe')
    monkeypatch.setattr(service, '_find', lambda appid: installed if appid == '1' else None)
    monkeypatch.setattr(games, 'analyze', lambda *args: {'target': str(root)})
    monkeypatch.setattr(games, 'running_under', lambda *args: False)
    return service, root, path, installed


def test_helix_settings_roundtrip_preserves_dll_and_unrelated_ini(setup):
    service, root, path, _ = setup
    assert service.image_settings('1') == {'supported': True, 'sharpness': {'enabled': None, 'value': None}, 'int8': 'auto', 'managed': False}
    result = service.set_image_settings('1', {'sharpness': {'enabled': True, 'value': .55}, 'int8': 'on'})
    assert result['sharpness'] == {'enabled': True, 'value': .55}
    assert result['int8'] == 'on' and result['managed']
    text = path.read_bytes().decode()
    assert ini.read(text, 'CAS.Enabled') == 'true'
    assert ini.read(text, 'Sharpness.Shader') == 'da'
    assert '\r\n' in text and b'provider' == (root / 'HelixSR/helixsr.dll').read_bytes()
    path.write_bytes(text.replace('Untouched=yes', 'Untouched=external').encode())
    service.restore_image_settings('1')
    assert path.read_bytes() == TEXT.replace('Untouched=yes', 'Untouched=external').encode()


def test_restore_does_not_overwrite_external_control_change(setup):
    service, _, path, _ = setup
    service.set_image_settings('1', {'int8': 'on'})
    path.write_bytes(path.read_bytes().replace(b'Int8=on', b'Int8=off'))
    assert service.restore_image_settings('1')['int8'] == 'off'


def test_restart_service_keeps_restoration(setup):
    service, _, _, _ = setup
    service.set_image_settings('1', {'int8': 'off'})
    service.state = service._load()
    assert service.restore_image_settings('1')['int8'] == 'auto'


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -.1, 1.01, True, '0.3'])
def test_reject_invalid_sharpness_without_writing(setup, value):
    service, _, path, _ = setup
    with pytest.raises(UpscalerError, match='image_settings_value'):
        service.set_image_settings('1', {'sharpness': {'enabled': True, 'value': value}})
    assert path.read_bytes() == TEXT.encode()


def test_own_optiscaler_sharpness_only_and_configure_preserves_slider(setup, monkeypatch):
    service, root, path, _ = setup
    install = {'target': str(root), 'options': {'sharpness': None}, 'build': 'fsr-4.1.2-lite'}
    service._game_state('1')['install'] = install
    monkeypatch.setattr(service, '_recipe', lambda *args: None)
    monkeypatch.setattr(service, '_identity', lambda *args: None)
    monkeypatch.setattr(games, 'analyze', lambda *args: {'inputs': {}})
    service.set_image_settings('1', {'sharpness': {'enabled': True, 'value': .47}})
    assert service.image_settings('1')['int8'] is None
    with pytest.raises(UpscalerError, match='image_settings_value'):
        service.set_image_settings('1', {'int8': 'on'})
    service.configure('1', {'quality': 'balanced', 'sharpness': None})
    assert ini.read(path.read_text(), 'Sharpness.Sharpness') == '0.47'
    assert ini.read(path.read_text(), 'Sharpness.OverrideSharpness') == 'true'
    assert ini.read(path.read_text(), 'CAS.Enabled') == 'true'


@pytest.mark.parametrize('engine', ['dll', 'proton', 'helixsr'])
def test_direct_engines_have_no_controls(setup, engine):
    service, root, path, _ = setup
    service._game_state('1')['install'] = {'engine': engine, 'target': str(root)}
    assert service.image_settings('1')['supported'] is False
    with pytest.raises(UpscalerError):
        service.set_image_settings('1', {'int8': 'on'})
    assert path.read_bytes() == TEXT.encode()


def test_reject_ambiguous_helix_identity(setup):
    service, root, _, _ = setup
    (root / 'OptiScaler.log').write_text('FFX upscaler: HLX DLSS\nHLX-FSR-4 own runtime active: yes')
    assert service.image_settings('1')['supported'] is False


@pytest.mark.parametrize('change', ['duplicate', 'case_duplicate', 'missing_key', 'invalid_int8'])
def test_bad_or_unsupported_layout_is_not_offered(setup, change):
    service, _, path, _ = setup
    text = TEXT
    replacements = {'duplicate': 'Int8=auto\r\nInt8=on', 'case_duplicate': 'Int8=auto\r\nint8=on',
                    'missing_key': '', 'invalid_int8': 'Int8=unknown'}
    text = text.replace('Int8=auto', replacements[change])
    path.write_bytes(text.encode())
    assert service.image_settings('1')['supported'] is False


def test_running_and_updating_guard(setup, monkeypatch):
    service, _, path, installed = setup
    monkeypatch.setattr(games, 'running_under', lambda *args: True)
    with pytest.raises(UpscalerError, match='running'):
        service.set_image_settings('1', {'int8': 'on'})
    monkeypatch.setattr(games, 'running_under', lambda *args: False)
    monkeypatch.setattr(service, '_find', lambda appid: dataclasses.replace(installed, state_flags=1024))
    with pytest.raises(UpscalerError, match='updat'):
        service.set_image_settings('1', {'int8': 'on'})
    assert path.read_bytes() == TEXT.encode()


def test_symlink_ini_is_refused(setup, tmp_path):
    service, _, path, _ = setup
    external = tmp_path / 'external.ini'
    external.write_bytes(TEXT.encode())
    path.unlink()
    path.symlink_to(external)
    assert service.image_settings('1')['reason'] == 'unsafe_path'
    with pytest.raises(UpscalerError, match='unsafe_path'):
        service.set_image_settings('1', {'int8': 'on'})
    assert external.read_bytes() == TEXT.encode()


def test_failed_replace_preserves_original_and_receipt(setup, monkeypatch):
    service, _, path, _ = setup
    def fail(*args, **kwargs):
        raise OSError('disk failure')
    monkeypatch.setattr(image_settings.os, 'replace', fail)
    with pytest.raises(OSError):
        service.set_image_settings('1', {'int8': 'on'})
    assert path.read_bytes() == TEXT.encode()
    assert not service._game_state('1').get('image_settings')

def test_file_replace_failure_keeps_prior_receipt_and_settings(setup, monkeypatch):
    service, _, path, _ = setup
    service.set_image_settings('1', {'int8': 'on'})
    before = path.read_bytes()
    old = image_settings.os.replace
    def fail_image(source, destination, *args, **kwargs):
        if str(source).startswith('.pdc-image-'):
            raise OSError('disk failure')
        return old(source, destination, *args, **kwargs)
    monkeypatch.setattr(image_settings.os, 'replace', fail_image)
    with pytest.raises(OSError):
        service.set_image_settings('1', {'int8': 'off'})
    assert path.read_bytes() == before
    assert service._game_state('1')['image_settings']['applied']['HelixSR.Int8'] == 'on'
    monkeypatch.setattr(image_settings.os, 'replace', old)
    assert service.restore_image_settings('1')['int8'] == 'auto'


def test_quality_change_preserves_external_sharpness_edit(setup, monkeypatch):
    service, root, path, _ = setup
    service._game_state('1')['install'] = {'target': str(root), 'options': {}, 'build': 'test'}
    monkeypatch.setattr(service, '_recipe', lambda *args: None)
    monkeypatch.setattr(service, '_identity', lambda *args: None)
    monkeypatch.setattr(games, 'analyze', lambda *args: {'inputs': {}})
    service.set_image_settings('1', {'sharpness': {'enabled': True, 'value': .47}})
    path.write_bytes(path.read_bytes().replace(b'Sharpness=0.47', b'Sharpness=0.62'))
    service.configure('1', {'quality': 'balanced', 'sharpness': None})
    assert ini.read(path.read_text(), 'Sharpness.Sharpness') == '0.62'
    service.restore_image_settings('1')
    assert ini.read(path.read_text(), 'Sharpness.Sharpness') == '0.62'


from test_upscalers import fake_catalog, steam  # noqa: E402


def test_reinstall_keeps_image_settings(steam, fake_catalog, tmp_path):
    from upscalers import catalog
    home, _ = steam
    service = UpscalerService(str(home), str(fake_catalog), 'rdna2', proc=str(tmp_path / 'proc'))
    archive = catalog.ASSETS[catalog.OPTISCALER_ARCHIVE]
    source = Path(fake_catalog) / 'cache' / archive.sha256 / 'unpacked/OptiScaler.ini'
    source.write_text(source.read_text() + '[Sharpness]\nOverrideSharpness=auto\nSharpness=auto\n[CAS]\nEnabled=auto\n')
    service.install('292030', {'build': 'fsr-test', 'quality': 'native'})
    service.set_image_settings('292030', {'sharpness': {'enabled': True, 'value': .56}})
    service.install('292030', {'build': 'fsr-test', 'quality': 'balanced'})
    assert service.image_settings('292030')['sharpness'] == {'enabled': True, 'value': .56}
    assert service.restore_image_settings('292030')['sharpness'] == {'enabled': None, 'value': None}


def test_disable_forces_zero_for_native_and_forced_rcas_consumers(setup):
    service, _, path, _ = setup
    service.set_image_settings('1', {'sharpness': {'enabled': True, 'value': .55}})
    result = service.set_image_settings('1', {'sharpness': {'enabled': False, 'value': .55}})
    # FFX uses positive sharpness internally; XeSS/DLSS can force RCAS despite CAS.Enabled=false.
    values = image_settings.values(path.read_text())
    assert values['CAS.Enabled'] == 'false'
    assert values['Sharpness.OverrideSharpness'] == 'true'
    assert float(values['Sharpness.Sharpness']) == 0
    assert result['sharpness'] == {'enabled': False, 'value': 0}


def test_positive_override_is_not_reported_disabled_when_cas_is_false(setup):
    service, _, path, _ = setup
    path.write_bytes(TEXT.replace('OverrideSharpness=auto', 'OverrideSharpness=true')
                    .replace('Sharpness=auto', 'Sharpness=0.55').replace('Enabled=auto', 'Enabled=false').encode())
    assert service.image_settings('1')['sharpness'] == {'enabled': None, 'value': .55}


def test_disable_also_stops_motion_sharpening_and_restore_preserves_it(setup):
    service, _, path, _ = setup
    original = TEXT.replace('Enabled=auto', 'Enabled=auto\r\nMotionSharpnessEnabled=true\r\nMotionSharpness=0.4')
    path.write_bytes(original.encode())
    result = service.set_image_settings('1', {'sharpness': {'enabled': False, 'value': .55}})
    assert result['sharpness'] == {'enabled': False, 'value': 0}
    assert ini.read(path.read_text(), 'CAS.MotionSharpnessEnabled') == 'false'
    assert ini.read(path.read_text(), 'CAS.MotionSharpness') == '0.4'
    service.restore_image_settings('1')
    assert path.read_bytes() == original.encode()


def test_manual_scaler_image_controls_work_before_any_game_log(setup):
    from test_upscalers_foreign_identity import scaler_install
    service, root, path, _ = setup
    (root / 'OptiScaler.log').unlink()
    scaler_install(root)
    assert service.image_settings('1')['int8'] == 'auto'
    assert service.set_image_settings('1', {'int8': 'on'})['int8'] == 'on'
    assert service.restore_image_settings('1')['int8'] == 'auto'


def test_incomplete_manual_scaler_marker_prevents_any_write(setup):
    from test_upscalers_foreign_identity import scaler_install
    service, root, path, _ = setup
    (root / 'OptiScaler.log').unlink()
    scaler_install(root)
    (root / 'HelixSR/helixsr.dll').unlink()
    before = path.read_bytes()
    assert service.image_settings('1')['supported'] is False
    with pytest.raises(UpscalerError, match='unsupported_layout'):
        service.set_image_settings('1', {'int8': 'on'})
    assert path.read_bytes() == before
