import struct

import pytest

from test_upscalers import APPID, _service, _write, fake_catalog as fake_catalog, proc as proc, steam as steam
from upscalers import luma, recipes


def image(*markers):
    data = bytearray(128)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 64)
    data[64:70] = b'PE\0\0\x64\x86'
    return bytes(data) + b'\0'.join(markers)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    target = tmp_path / 'game/End/Binaries/Win64'
    _write(target / 'Luma-Final Fantasy VII Remake.addon', image(
        b'Final Fantasy VII Remake Luma mod', b'Luma for "Final Fantasy VII Remake" is developed by Izueh and Pumbo'))
    _write(target / 'ReShade64.dll', image(b'ReShadeRegisterAddon'))
    _write(target / 'OptiScaler.ini', '[Plugins]\nLoadReshade=true\n')
    _write(target / 'Luma/Final Fantasy VII Remake/Luma_FF7R_Output_SDR_Tonemap.hlsl', 'shader')
    _write(target / 'Luma/d3dcompiler_47.dll', image())
    monkeypatch.setattr(luma.pe, 'version_strings', lambda path: {'ProductName': 'ReShade', 'OriginalFilename': 'ReShade64.dll'})
    return tmp_path / 'game', target


def test_recognizes_components_and_configured_loader_without_claiming_runtime(prepared):
    root, target = prepared
    assert luma.detected(root, target, '1462040') is True
    assert luma.detected(root, target, '403640') is False


@pytest.mark.parametrize('name', ['Luma-Final Fantasy VII Remake.addon', 'ReShade64.dll',
                                  'Luma/Final Fantasy VII Remake/Luma_FF7R_Output_SDR_Tonemap.hlsl',
                                  'Luma/d3dcompiler_47.dll', 'OptiScaler.ini'])
def test_incomplete_installation_is_not_detected(prepared, name):
    root, target = prepared
    (target / name).unlink()
    assert luma.detected(root, target, '1462040') is False


@pytest.mark.parametrize('value', ['false', 'auto', ''])
def test_loader_must_be_enabled(prepared, value):
    root, target = prepared
    (target / 'OptiScaler.ini').write_text('[Plugins]\nLoadReshade=' + value)
    assert luma.detected(root, target, '1462040') is False


def test_other_reshade_or_addon_name_is_not_luma_evidence(prepared, monkeypatch):
    root, target = prepared
    monkeypatch.setattr(luma.pe, 'version_strings', lambda path: {'ProductName': 'Other loader', 'OriginalFilename': 'ReShade64.dll'})
    assert luma.detected(root, target, '1462040') is False
    monkeypatch.setattr(luma.pe, 'version_strings', lambda path: {'ProductName': 'ReShade', 'OriginalFilename': 'ReShade64.dll'})
    (target / 'Luma-Final Fantasy VII Remake.addon').write_bytes(image(b'Other game Luma mod'))
    assert luma.detected(root, target, '1462040') is False


def test_names_without_real_pe_and_addon_host_do_not_match(prepared):
    root, target = prepared
    (target / 'ReShade64.dll').write_bytes(image())
    assert luma.detected(root, target, '1462040') is False
    (target / 'ReShade64.dll').write_bytes(image(b'ReShadeRegisterAddon'))
    (target / 'Luma-Final Fantasy VII Remake.addon').write_bytes(b'Final Fantasy VII Remake Luma mod')
    assert luma.detected(root, target, '1462040') is False


def test_symlinks_and_outside_targets_are_not_read(prepared, tmp_path):
    root, target = prepared
    path = target / 'ReShade64.dll'
    content = path.read_bytes()
    path.unlink()
    outside = _write(tmp_path / 'outside.dll', content)
    path.symlink_to(outside)
    assert luma.detected(root, target, '1462040') is False
    assert luma.detected(root, tmp_path, '1462040') is False


def test_absent_and_oversize_are_not_detected(prepared):
    root, target = prepared
    assert luma.detected(root, None, '1462040') is False
    with (target / 'Luma-Final Fantasy VII Remake.addon').open('wb') as stream:
        stream.truncate(luma._MAX_ADDON + 1)
    assert luma.detected(root, target, '1462040') is False


def test_game_info_preserves_requirement_and_adds_evidence_only_for_luma(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    monkeypatch.setattr(service, '_recipe', lambda *args: recipes.Recipe('1462040', needs=('luma',)))
    calls = []
    monkeypatch.setattr(luma, 'detected', lambda *args: calls.append(args) or True)
    info = service.game(APPID)['recipe_info']
    assert info['needs'] == ['luma']
    assert info['luma_detected'] is True
    assert len(calls) == 1
    monkeypatch.setattr(service, '_recipe', lambda *args: recipes.Recipe(APPID, needs=('mod',)))
    assert 'luma_detected' not in service.game(APPID)['recipe_info']
    assert len(calls) == 1


def test_recognizes_persona_5_royal_next_to_the_executable(tmp_path, monkeypatch):
    root = tmp_path / 'game'
    _write(root / 'Luma-Persona 5 Royal.addon', image(b'Persona 5 Royal Luma mod'))
    _write(root / 'ReShade64.dll', image(b'ReShadeRegisterAddon'))
    _write(root / 'OptiScaler.ini', '[Plugins]\nLoadReshade=true\n')
    _write(root / 'Luma/Persona 5 Royal/Luma_DecodeMotionVector.hlsl', 'shader')
    _write(root / 'Luma/d3dcompiler_47.dll', image())
    monkeypatch.setattr(luma.pe, 'version_strings', lambda path: {'ProductName': 'ReShade', 'OriginalFilename': 'ReShade64.dll'})
    assert luma.detected(root, root, '1687950') is True
    assert luma.detected(root, root, '1462040') is False
    (root / 'Luma-Persona 5 Royal.addon').write_bytes(image(b'Final Fantasy VII Remake Luma mod'))
    assert luma.detected(root, root, '1687950') is False
