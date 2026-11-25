import hashlib
from dataclasses import replace
from pathlib import Path
import pytest
from test_upscalers import APPID, _service, _write, steam, fake_catalog, dll_catalog, proc
from upscalers import catalog
from upscalers.catalog import Asset
from upscalers.service import UpscalerError

PROVIDER = "amd_fidelityfx_upscaler_dx12.dll"
LOADER = "amd_fidelityfx_loader_dx12.dll"
FG = "amd_fidelityfx_framegeneration_dx12.dll"

@pytest.fixture
def bridge(dll_catalog, monkeypatch):
    additions = {}
    for name in (LOADER, FG):
        payload = ("bridge " + name).encode()
        asset = Asset(name, name, hashlib.sha256(payload).hexdigest(), len(payload), ("http://invalid",))
        monkeypatch.setitem(catalog.ASSETS, name, asset)
        _write(Path(dll_catalog) / "cache" / asset.sha256 / name, payload)
        additions[name] = name
    monkeypatch.setitem(catalog.BUILDS, "dll-test", replace(catalog.BUILDS["dll-test"], legacy_replace=additions))
    return dll_catalog

@pytest.mark.parametrize("existing_fg", [False, True])
def test_legacy_bridge_preserves_modern_loader_and_restores(steam, bridge, proc, existing_fg):
    _, root = steam
    modern = _write(root / "bin/x64_dx12" / LOADER.upper(), b"modern loader")
    legacy = _write(root / "_storage_/AMD_FIDELITYFX_DX12.DLL", b"legacy")
    sibling = _write(legacy.parent / LOADER, b"sibling loader")
    fg = legacy.parent / (FG.upper() if existing_fg else FG)
    if existing_fg:
        _write(fg, b"existing FG")
    service = _service(steam, bridge, proc)
    for _ in range(2):
        service.install(APPID, {"build": "dll-test"})
        assert modern.read_bytes() == b"modern loader"
        assert sibling.read_bytes() == b"sibling loader"
        assert legacy.read_bytes() == ("bridge " + LOADER).encode()
        assert (legacy.parent / PROVIDER).read_bytes() == b"standalone upscaler"
        assert fg.read_bytes() == (b"existing FG" if existing_fg else ("bridge " + FG).encode())
    service.uninstall(APPID)
    assert legacy.read_bytes() == b"legacy"
    assert not (legacy.parent / PROVIDER).exists()
    assert fg.exists() == existing_fg
    assert modern.read_bytes() == b"modern loader"

def test_bridge_does_not_allow_unrelated_orphan_loader(steam, bridge, proc):
    _, root = steam
    legacy = _write(root / "_storage_/amd_fidelityfx_dx12.dll", b"legacy")
    _write(root / "orphan" / LOADER, b"orphan")
    with pytest.raises(UpscalerError, match="dll_unsupported"):
        _service(steam, bridge, proc).install(APPID, {"build": "dll-test"})
    assert legacy.read_bytes() == b"legacy"

def test_bridge_metadata_separates_modern_replacements(bridge):
    info = next(item for item in catalog.describe("rdna2") if item["id"] == "dll-test")
    assert info["dll_names"] == [PROVIDER]
    assert set(info["dll_legacy_names"]) == {LOADER, FG}


@pytest.mark.parametrize("unsafe_name", [PROVIDER, FG])
def test_bridge_rejects_symlink_before_replacing_current_install(steam, bridge, proc, unsafe_name):
    _, root = steam
    service = _service(steam, bridge, proc)
    service.install(APPID, {"build": "dll-test"})
    legacy = _write(root / "_storage_/amd_fidelityfx_dx12.dll", b"legacy")
    outside = _write(root.parent / "outside.dll", b"outside")
    (legacy.parent / unsafe_name).symlink_to(outside)
    with pytest.raises(UpscalerError, match="unsafe_folder"):
        service.install(APPID, {"build": "dll-test"})
    assert (root / "bin/x64_dx12" / PROVIDER).read_bytes() == b"standalone upscaler"
    assert legacy.read_bytes() == b"legacy"
    assert outside.read_bytes() == b"outside"


def test_transition_prepares_bridge_before_optiscaler_removal(steam, bridge, proc, monkeypatch):
    _, root = steam
    service = _service(steam, bridge, proc)
    service.install(APPID, {"build": "fsr-test"})
    legacy = _write(root / "_storage_/amd_fidelityfx_dx12.dll", b"original legacy")
    guard = service._guard

    def before_restore(*args, **kwargs):
        installed, analysis, target = guard(*args, **kwargs)
        analysis["dll_targets"] = [path for path in analysis["dll_targets"] if path != "_storage_/amd_fidelityfx_dx12.dll"]
        return installed, analysis, target

    monkeypatch.setattr(service, "_guard", before_restore)
    ensure = service.cache.ensure
    requested = []

    def download(asset, *args, **kwargs):
        assert service.state["games"][APPID]["install"]["build"] == "fsr-test"
        requested.append(asset.id)
        return ensure(asset, *args, **kwargs)

    monkeypatch.setattr(service.cache, "ensure", download)
    service.install(APPID, {"build": "dll-test"})
    assert {LOADER, FG} <= set(requested)
    assert legacy.read_bytes() == ("bridge " + LOADER).encode()
    assert service.state["games"][APPID]["install"]["engine"] == "dll"
    service.uninstall(APPID)
    assert legacy.read_bytes() == b"original legacy"
