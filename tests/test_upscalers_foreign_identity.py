import json

import pytest

from upscalers import games
from test_upscalers import steam, fake_catalog, proc


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_helix_manifest_does_not_guess_variant_from_fsr_provider(tmp_path):
    write(tmp_path, "helixsr-install.json", json.dumps({"helixsr": "1.8.1", "files": ["amd_fidelityfx_upscaler_dx12.dll"]}))
    write(tmp_path, "OptiScaler.ini", "[FSR]")
    assert games.foreign_identity(tmp_path) == {
        "engine": "helixsr", "variant": "unknown", "evidence": ["helixsr-install.json"], "manifest_error": False,
    }


@pytest.mark.parametrize(("name", "line", "variant"), [
    ("OptiScaler.log", "[I] FFX upscaler: HLX DLSS (version name test, index 1)", "dlss"),
    ("HelixSR-fsrfg/helixsr.log", "FFX upscaler: HLX DLSS (version name test)", "dlss"),
    ("HLX_FSR.log", "HLX-FSR-4 own runtime active: int8p-s-std-k01 (tier 9)", "fsr"),
    ("_storage_/HLX_FSR.log", "HLX-FSR-4 own runtime active: int8p-s-std-k01 (tier 9)", "fsr"),
])
def test_explicit_log_identity_is_not_an_activity_verdict(tmp_path, name, line, variant):
    write(tmp_path, "helixsr-install.json", "{}")
    write(tmp_path, name, line)
    result = games.foreign_identity(tmp_path)
    assert result["engine"] == "helixsr"
    assert result["variant"] == variant
    assert result["manifest_error"] is False
    assert set(result) == {"engine", "variant", "evidence", "manifest_error"}


@pytest.mark.parametrize("content", ["{", "null", "[]", '{"files": 4}', '{"files": "dxgi.dll"}', '{"files": [null]}'])
def test_invalid_manifest_is_reported_without_guessing(tmp_path, content):
    write(tmp_path, "helixsr-install.json", content)
    write(tmp_path, "OptiScaler.log", "FFX upscaler: HLX DLSS (version name test)")
    result = games.foreign_identity(tmp_path)
    assert result["engine"] == "helixsr"
    assert result["variant"] == "unknown"
    assert result["manifest_error"] is True


def test_conflicting_helix_logs_preserve_unknown_variant(tmp_path):
    write(tmp_path, "OptiScaler.log", "FFX upscaler: HLX DLSS (version name test)")
    write(tmp_path, "HLX_FSR.log", "HLX-FSR-4 own runtime active: model")
    assert games.foreign_identity(tmp_path)["variant"] == "unknown"


def test_optiscaler_and_unrecognized_marker_are_distinct(tmp_path):
    write(tmp_path, "FRAMEGEN_PATCH", "")
    assert games.foreign_identity(tmp_path)["engine"] == "unknown"
    write(tmp_path, "OptiScaler.ini", "[FSR]")
    assert games.foreign_identity(tmp_path)["engine"] == "optiscaler"


def test_symlinked_log_directory_does_not_supply_identity(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    outside = tmp_path / "outside"
    write(outside, "helixsr.log", "FFX upscaler: HLX DLSS (version name test)")
    (game / "HelixSR-fsrfg").symlink_to(outside, target_is_directory=True)
    write(game, "helixsr-install.json", "{}")
    assert games.foreign_identity(game)["variant"] == "unknown"


def test_symlinked_manifest_is_unreadable_not_followed(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    outside = write(tmp_path, "outside.json", "{}")
    (game / "helixsr-install.json").symlink_to(outside)
    assert games.foreign_identity(game)["manifest_error"] is True


def test_oversized_or_invalid_unicode_manifest_is_reported(tmp_path):
    marker = write(tmp_path, "helixsr-install.json", " " * (games._FOREIGN_READ_LIMIT + 1))
    assert games.foreign_identity(tmp_path)["manifest_error"] is True
    marker.write_bytes(b"\xff")
    assert games.foreign_identity(tmp_path)["manifest_error"] is True


def test_analysis_preserves_ownership_and_foreign_boolean(tmp_path, monkeypatch):
    write(tmp_path, "game.exe", "MZ")
    monkeypatch.setattr(games.pe, "graphics_apis", lambda path: ["d3d12"])
    write(tmp_path, "helixsr-install.json", "{}")
    result = games.analyze(tmp_path)
    assert result["foreign"] is True
    assert result["foreign_identity"]["engine"] == "helixsr"
    (tmp_path / games.MANIFEST_DIR).mkdir()
    result = games.analyze(tmp_path)
    assert result["foreign"] is False
    assert result["foreign_identity"] is None


def test_service_rejects_helix_dlss_adoption_without_moving_files(steam, fake_catalog, proc):
    from test_upscalers import APPID, _service
    from upscalers.service import UpscalerError
    _, game = steam
    target = game / "bin/x64_dx12"
    write(target, "OptiScaler.log", "FFX upscaler: HLX DLSS (version name test)")
    payload = write(target, "HelixSR-fsrfg/network.bin", "compiled-network")
    service = _service(steam, fake_catalog, proc)
    assert service.game(APPID)["analysis"]["foreign_identity"]["variant"] == "dlss"
    with pytest.raises(UpscalerError, match="foreign_helix"):
        service.adopt_foreign(APPID)
    assert payload.read_text() == "compiled-network"
    assert (target / "OptiScaler.log").exists()


SCALER_MANIFEST = '# HelixSR Scaler, installed by HelixSR Desktop\n# version=\n# layout=ngx\nname=dxgi.dll\nLicenses/DirectX_LICENSE.txt\nLicenses/FidelityFX_v2_LICENSE.md\nLicenses/OptiPatcher_LICENSE.txt\nLicenses/OptiScaler_LICENSE.txt\nLicenses/XeSS_LICENSE.txt\ndxgi.dll\nOptiScaler.ini\nOptiScaler/D3D12_OptiScaler/D3D12Core.dll\nOptiScaler/amd_fidelityfx_framegeneration_dx12.dll\nOptiScaler/amd_fidelityfx_loader_dx12.dll\nOptiScaler/amd_fidelityfx_upscaler_dx12.amd.dll\nOptiScaler/amd_fidelityfx_upscaler_dx12.dll\nOptiScaler/amd_fidelityfx_vk.dll\nOptiScaler/libxell.dll\nOptiScaler/libxess.dll\nOptiScaler/libxess_dx11.dll\nOptiScaler/libxess_fg.dll\nOptiScaler/plugins/OptiPatcher.asi\nHelixSR/helixsr.dll\n'


def scaler_install(root):
    write(root, 'HelixSR-Scaler.files', SCALER_MANIFEST)
    write(root, 'OptiScaler.ini', '; HelixSR Scaler\n[HelixSR]\nInt8=auto\n[Sharpness]\nOverrideSharpness=auto\nSharpness=auto\n[CAS]\nEnabled=auto\n')
    write(root, 'dxgi.dll', 'MZproxy')
    write(root, 'HelixSR/helixsr.dll', 'MZprovider')


def test_official_scaler_manifest_identifies_manual_dlss_before_first_run(tmp_path):
    scaler_install(tmp_path)
    result = games.foreign_identity(tmp_path)
    assert result == {'engine': 'helixsr', 'variant': 'dlss', 'manifest_error': False,
                      'evidence': ['HelixSR-Scaler.files']}
    assert not (tmp_path / 'OptiScaler.log').exists()


@pytest.mark.parametrize('replacement', [
    SCALER_MANIFEST.replace('HelixSR/helixsr.dll\n', ''),
    SCALER_MANIFEST + '../external.dll\n',
    SCALER_MANIFEST + '/tmp/external.dll\n',
    SCALER_MANIFEST + 'HelixSR\\helixsr.dll\n',
    SCALER_MANIFEST + '# layout=ngx\n',
    SCALER_MANIFEST + 'dxgi.dll\n',
])
def test_invalid_scaler_manifest_does_not_offer_replacement_or_settings(tmp_path, replacement):
    scaler_install(tmp_path)
    write(tmp_path, 'HelixSR-Scaler.files', replacement)
    result = games.foreign_identity(tmp_path)
    assert result['engine'] == 'helixsr'
    assert result['variant'] == 'unknown' and result['manifest_error']


def test_unknown_scaler_layout_is_preserved_without_guessing(tmp_path):
    scaler_install(tmp_path)
    write(tmp_path, 'HelixSR-Scaler.files', SCALER_MANIFEST.replace('layout=ngx', 'layout=other'))
    write(tmp_path, 'OptiScaler.log', 'FFX upscaler: HLX DLSS')
    assert games.foreign_identity(tmp_path)['variant'] == 'unknown'


@pytest.mark.parametrize('name', ['dxgi.dll', 'HelixSR/helixsr.dll'])
def test_manifest_requires_real_provider_and_proxy(tmp_path, name):
    scaler_install(tmp_path)
    (tmp_path / name).write_bytes(b'not a DLL')
    assert games.foreign_identity(tmp_path)['manifest_error'] is True


def test_scaler_marker_or_provider_symlink_is_rejected(tmp_path):
    scaler_install(tmp_path)
    provider = tmp_path / 'HelixSR/helixsr.dll'
    provider.unlink()
    provider.symlink_to(tmp_path / 'dxgi.dll')
    assert games.foreign_identity(tmp_path)['manifest_error'] is True
    provider.unlink()
    provider.write_bytes(b'MZprovider')
    marker = tmp_path / 'HelixSR-Scaler.files'
    marker.rename(tmp_path / 'saved.files')
    marker.symlink_to(tmp_path / 'saved.files')
    assert games.foreign_identity(tmp_path)['manifest_error'] is True


def test_scaler_marker_alone_protects_foreign_installation(tmp_path, monkeypatch):
    write(tmp_path, 'game.exe', 'MZ')
    write(tmp_path, 'HelixSR-Scaler.files', SCALER_MANIFEST)
    monkeypatch.setattr(games.pe, 'graphics_apis', lambda path: ['d3d12'])
    analysis = games.analyze(tmp_path)
    assert analysis['foreign'] is True
    assert analysis['foreign_identity']['engine'] == 'helixsr'
    assert analysis['foreign_identity']['manifest_error'] is True
