from pathlib import Path

import pytest

from upscalers import catalog, diagnostics
from upscalers.service import UpscalerService
from test_upscalers import APPID, _service, _write, proc, steam


BUILD = "fsr-4.1.2-lite-igpu-dll"
PROVIDER = "amd_fidelityfx_upscaler_dx12.dll"


def test_lite412_igpu_uses_pinned_exact_archive():
    build = catalog.BUILDS[BUILD]
    asset = catalog.ASSETS[build.replace[PROVIDER]]
    assert build.engine == "dll"
    assert build.version == "4.1.2"
    assert build.models == (("lite", {}),)
    assert asset.filename == "fsr4.1.2-igpu-cyboman-rdna3-2026-11-05.7z"
    assert asset.size == 9553046
    assert asset.sha256 == "6553cfeaa824fd1fa36985278e5ce835d27bbb758e99a1db5efaf331fe72dc4f"
    assert asset.member == "4.1.2l-exact/amd_fidelityfx_upscaler_dx12.dll"
    assert asset.urls == ("https://github.com/zgauthier2000/fsr4-shader-performance-overrides/releases/download/dll-2026-11-05/" + asset.filename,)
    assert build.legacy_replace == catalog.BUILDS["fsr-4.1.2-lite-dll"].legacy_replace
    assert asset != catalog.ASSETS[catalog.BUILDS["fsr-4.1.2-lite-dll"].replace[PROVIDER]]


def test_ally_preserves_explicit_sdk_and_lite_choices(tmp_path, monkeypatch):
    service = UpscalerService(str(tmp_path), str(tmp_path / "state"), "rdna3", device="rog_ally")
    calls = []
    monkeypatch.setattr(service, "_install_dll", lambda appid, build, choice: calls.append(build.id) or {"ok": True})
    for build_id in ("fsr-4.1.2-dll", BUILD):
        assert service.install("42", {"build": build_id}) == {"ok": True}
    assert calls == ["fsr-4.1.2-dll", BUILD]
    rows = {row["id"]: row for row in service.overview()["builds"]}
    assert rows[BUILD]["supported"]
    assert rows["fsr-4.1.2-dll"]["supported"]


def test_lite412_igpu_mixed_targets_restore_without_runtime_claim(steam, proc, tmp_path, monkeypatch):
    _, game = steam
    folder = game / "bin/x64_dx12"
    names = [PROVIDER, "amd_fidelityfx_loader_dx12.dll", "_storage_/amd_fidelityfx_dx12.dll",
             "_storage_/amd_fidelityfx_loader_dx12.dll", "_storage_/" + PROVIDER]
    originals = {name: ("original:" + name).encode() for name in names}
    for name, data in originals.items():
        _write(folder / name, data)
    service = _service(steam, tmp_path / "state", proc)
    service.gpu, service.device = "rdna3", "rog_ally"
    build = catalog.BUILDS[BUILD]
    payloads = {asset.id: _write(tmp_path / "payloads" / asset.id / Path(asset.member).name, asset.id)
                for asset in catalog.build_assets(build)}
    monkeypatch.setattr(service.cache, "ensure", lambda asset, *_: payloads[asset.id])
    service.install(APPID, {"build": BUILD})
    assert (folder / PROVIDER).read_bytes() == build.replace[PROVIDER].encode()
    assert (folder / "_storage_" / PROVIDER).read_bytes() == build.replace[PROVIDER].encode()
    assert (folder / "_storage_/amd_fidelityfx_dx12.dll").read_bytes() == build.legacy_replace["amd_fidelityfx_loader_dx12.dll"].encode()
    observed = diagnostics.snapshot({"engine": "dll", "build": BUILD, "target": str(folder)})["observed"]
    assert observed["result"] == "unverifiable"
    assert observed["source"] == "unavailable"
    service.uninstall(APPID)
    for name, data in originals.items():
        assert (folder / name).read_bytes() == data
    assert not (folder / "_storage_/amd_fidelityfx_framegeneration_dx12.dll").exists()


@pytest.mark.parametrize("device", ["rog_ally", "rog_ally_x", "legion_go", "legion_go_s", "rog_xbox_ally_x", "desktop", ""])
@pytest.mark.parametrize("gpu", ["rdna2", "rdna3", "rdna35", "rdna4", "intel", "unknown"])
def test_lite412_igpu_gate_requires_known_z1_device_and_rdna3(device, gpu):
    expected = gpu == "rdna3" and device in {"rog_ally", "rog_ally_x", "legion_go", "legion_go_s"}
    build = catalog.BUILDS[BUILD]
    assert catalog.build_supported(build, gpu, device) is expected
    row = next(row for row in catalog.describe(gpu, device) if row["id"] == BUILD)
    assert row["available"]
    assert row["supported"] is expected


def test_lite412_igpu_explicit_force_is_preserved(tmp_path, monkeypatch):
    service = UpscalerService(str(tmp_path), str(tmp_path / "state"), "rdna3", device="desktop")
    calls = []
    monkeypatch.setattr(service, "_install_dll", lambda appid, build, choice: calls.append(build.id) or {"ok": True})
    assert service.install("42", {"build": BUILD, "force": True}) == {"ok": True}
    assert calls == [BUILD]
