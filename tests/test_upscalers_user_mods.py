import hashlib
import json
import os

import pytest

from upscalers import user_mods


APPID = "1245620"
FILES = {
    "D3D12.dll": 521216,
    "ERSS-FG.dll": 14648832,
    "ERSSReShadeStub.addon": 455168,
    "ERSS2/bin/amd_fidelityfx_framegeneration_dx12.dll": 38245640,
    "ERSS2/bin/amd_fidelityfx_loader_dx12.dll": 25864,
    "ERSS2/bin/amd_fidelityfx_upscaler_dx12.dll": 22348552,
}
HEADER = "# Version: 4.14.1-0 (86498e0) Release"


@pytest.fixture
def stored_mod(tmp_path, monkeypatch):
    store = user_mods.Store(tmp_path / "store")
    root = store.root / APPID
    for name, size in FILES.items():
        path = root / "files" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            handle.write(b"MZ")
            handle.truncate(size)
    (root / "meta.json").write_text(json.dumps({
        "filename": "ERSS-FG.7z", "target": "Game", "id": "archive@1", "files": sorted(FILES),
        "verbs": ["vcrun2022"],
    }))
    monkeypatch.setattr(user_mods.pe, "imported_dlls", lambda path: {"msvcp140.dll"})
    return store, root / "files"


@pytest.mark.parametrize("from_resource", [True, False])
def test_recognizes_erss_release_from_the_original_binary(stored_mod, monkeypatch, from_resource):
    store, files = stored_mod
    if from_resource:
        monkeypatch.setattr(user_mods.pe, "version_strings", lambda path: {"ProductVersion": "4.14.1.0"})
    else:
        with (files / "ERSS-FG.dll").open("r+b") as handle:
            handle.seek(256)
            handle.write(b"\0" + b"86498e0" + b"\0")
    assert store.status(APPID)["tested_release"] == "erss-fg-4.14.1"


def test_requires_erss_package_files_at_the_observed_sizes(stored_mod, monkeypatch):
    store, files = stored_mod
    monkeypatch.setattr(user_mods.pe, "version_strings", lambda path: {"FileVersion": "4.14.1.0"})
    (files / "D3D12.dll").write_bytes(b"different DLL")
    assert "tested_release" not in store.status(APPID)


def test_erss_filename_and_package_shape_do_not_identify_the_release(stored_mod):
    store, _ = stored_mod
    assert "tested_release" not in store.status(APPID)


def test_recognizes_runtime_header_only_for_the_same_installed_mod(stored_mod, tmp_path):
    store, files = stored_mod
    target = tmp_path / "game" / "Game"
    receipt = target / ".pdc-upscaler" / "manifest.json"
    receipt.parent.mkdir(parents=True)
    dll = target / "ERSS-FG.dll"
    dll.write_bytes((files / dll.name).read_bytes())
    digest = hashlib.sha256(dll.read_bytes()).hexdigest()
    receipt.write_text(json.dumps({"owned": [dll.name], "files": {dll.name: digest}}))
    config = target / "ERSS2" / "ERSS-FG.toml"
    config.parent.mkdir()
    config.write_text(HEADER + "\n[Renderer]\nScalingMode = \"FSR3U\"\n")
    after_install = config.stat().st_mtime
    install = {"target": str(target), "installed_at": after_install - 1, "mod": {"id": "archive@1"}}

    assert store.status(APPID, install=install)["tested_release"] == "erss-fg-4.14.1"
    assert "tested_release" not in store.status(APPID, install={**install, "mod": {"id": "another archive"}})

    os.utime(config, (after_install - 2, after_install - 2))
    assert "tested_release" not in store.status(APPID, install=install)

    os.utime(config, (after_install, after_install))
    with dll.open("r+b") as handle:
        handle.seek(32)
        handle.write(b"different")
    assert "tested_release" not in store.status(APPID, install=install)


def test_requires_the_visual_cpp_dependency_from_the_erss_binary(stored_mod, monkeypatch):
    store, _ = stored_mod
    monkeypatch.setattr(user_mods.pe, "imported_dlls", lambda path: {"kernel32.dll"})
    monkeypatch.setattr(user_mods.pe, "version_strings", lambda path: {"FileVersion": "4.14.1"})
    assert "tested_release" not in store.status(APPID)
