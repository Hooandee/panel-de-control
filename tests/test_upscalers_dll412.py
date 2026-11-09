from pathlib import Path

import pytest

from upscalers import catalog
from upscalers.service import UpscalerError
from test_upscalers import APPID, _service, _write, proc, steam


BUILD = "fsr-4.1.2-lite-dll"
PROVIDER = "amd_fidelityfx_upscaler_dx12.dll"


@pytest.mark.parametrize("device", ["steam_deck_lcd", "steam_deck_oled", "legion_go_s", "z2_a", ""])
def test_sdk412_device_gate_only_excludes_steam_deck(device):
    sdk = catalog.BUILDS["fsr-4.1.2-dll"]
    expected = device not in {"steam_deck_lcd", "steam_deck_oled"}
    assert catalog.build_supported(sdk, "rdna2", device) == expected
    rows = {row["id"]: row for row in catalog.describe("rdna2", device)}
    assert rows[sdk.id]["supported"] == expected
    assert rows[BUILD]["supported"]
    assert catalog.build_supported(sdk, "rdna2")
    for gpu in ("rdna3", "rdna35", "rdna4", "intel", "unknown"):
        assert catalog.build_supported(sdk, gpu, "other_device") == (gpu in catalog.AMD)


def test_dll412_lite_metadata_and_sdk_assets_are_separate():
    build = catalog.BUILDS[BUILD]
    assert build.engine == "dll" and build.version == "4.1.2"
    assert build.models == (("lite", {}),)
    asset = catalog.ASSETS[build.replace[PROVIDER]]
    assert asset.filename == "fsr4.1.2-igpu-cyboman-rdna2-2026-11-05.7z"
    assert asset.member == "4.1.2l-exact/amd_fidelityfx_upscaler_dx12.dll"
    assert asset.size == 9567439
    assert asset.sha256 == "da7c7681bffe7ac60a01e859d5b107900d963557793ef67ddcfd03a832e1c03f"
    assert asset.urls == ("https://github.com/zgauthier2000/fsr4-shader-performance-overrides/releases/download/dll-2026-11-05/" + asset.filename,)
    assert build.legacy_replace == catalog.BUILDS["fsr-4.1.1-lite-dll"].legacy_replace
    sdk = catalog.BUILDS["fsr-4.1.2-dll"]
    assert sdk.gpus == catalog.AMD
    assert sdk.replace == {f"amd_fidelityfx_{part}_dx12.dll": f"fsr-4.1.2-dll-{part}" for part in ("loader", "upscaler", "framegeneration")}
    assert all(catalog.ASSETS[key].sha256 == "7b6300ccf19f91ce27b2729f53aa1e4a907e6ea46ae9e93d313a206e2aee68ff" for key in sdk.replace.values())
    for gpu in ("rdna2", "rdna3", "rdna35", "rdna4", "intel", "unknown"):
        row = next(row for row in catalog.describe(gpu) if row["id"] == BUILD)
        assert row["available"]
        assert row["supported"] == (gpu == "rdna2")


@pytest.mark.parametrize("gpu", ["rdna3", "rdna35", "rdna4", "intel", "unknown"])
def test_dll412_lite_installs_on_any_gpu_when_chosen(steam, proc, tmp_path, monkeypatch, gpu):
    service = _service(steam, tmp_path / "state", proc)
    service.gpu = gpu
    calls = []
    monkeypatch.setattr(service, "_install_dll", lambda appid, build, choice: calls.append(build.id) or {"ok": True})
    assert service.install(APPID, {"build": BUILD}) == {"ok": True}
    assert calls == [BUILD]


def test_dll412_lite_mixed_targets_restore_original_bytes(steam, proc, tmp_path, monkeypatch):
    _, game = steam
    folder = game / "bin/x64_dx12"
    names = [PROVIDER, "amd_fidelityfx_loader_dx12.dll", "_storage_/amd_fidelityfx_dx12.dll",
             "_storage_/amd_fidelityfx_loader_dx12.dll", "_storage_/" + PROVIDER]
    originals = {name: ("original:" + name).encode() for name in names}
    for name, data in originals.items():
        _write(folder / name, data)
    service = _service(steam, tmp_path / "state", proc)
    build = catalog.BUILDS[BUILD]
    payloads = {}
    for asset in catalog.build_assets(build):
        payloads[asset.id] = _write(tmp_path / "payloads" / asset.id / Path(asset.member).name, asset.id)
    monkeypatch.setattr(service.cache, "ensure", lambda asset, *_: payloads[asset.id])
    service.install(APPID, {"build": BUILD})
    assert (folder / PROVIDER).read_bytes() == build.replace[PROVIDER].encode()
    assert (folder / "_storage_" / PROVIDER).read_bytes() == build.replace[PROVIDER].encode()
    assert (folder / "_storage_/amd_fidelityfx_dx12.dll").read_bytes() == build.legacy_replace["amd_fidelityfx_loader_dx12.dll"].encode()
    service.uninstall(APPID)
    for name, data in originals.items():
        assert (folder / name).read_bytes() == data
    assert not (folder / "_storage_/amd_fidelityfx_framegeneration_dx12.dll").exists()
