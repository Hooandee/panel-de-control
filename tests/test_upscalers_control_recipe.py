import pytest

from upscalers import games, ini, recipes
from upscalers.service import UpscalerService
from test_upscalers import fake_catalog, dll_catalog


@pytest.fixture
def control(tmp_path, fake_catalog, monkeypatch):
    root = tmp_path / "Control"
    root.mkdir()
    (root / "ControlLauncher.exe").write_bytes(b"MZ" + b"\0" * 64)
    (root / "Control_DX12.exe").write_bytes(b"MZ" + b"\0" * 4096)
    (root / "nvngx_dlss.dll").write_bytes(b"original dlss")
    (root / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"original fsr")
    installed = games.Installed("870780", "Control Ultimate Edition", root, 4, "Control_DX12.exe")
    service = UpscalerService(str(tmp_path), str(fake_catalog), "rdna2", proc=str(tmp_path / "proc"))
    monkeypatch.setattr(service, "_find", lambda appid: installed if appid == installed.appid else None)
    return service, root


def test_control_recipe_is_exact_and_keeps_wiki_metadata():
    recipe = recipes.recipe_for("870780")
    assert recipe.ini == {"Spoofing.Dxgi": "false"}
    assert not recipe.files and not recipe.native_dlls and not recipe.args
    assert recipe.status == "works"
    assert recipes.RECIPES.get("870781") is None


def test_control_install_disables_launcher_spoofing_and_configure_keeps_it(control):
    service, root = control
    service.install("870780", {"build": "fsr-test", "quality": "native"})
    path = root / "OptiScaler.ini"
    assert ini.read(path.read_text(), "Spoofing.Dxgi") == "false"
    assert "Spoofing.Dxgi" in service.game("870780")["install"]["managed"]
    service.configure("870780", {"quality": "balanced"})
    assert ini.read(path.read_text(), "Spoofing.Dxgi") == "false"
    service.uninstall("870780")
    assert not path.exists()
    assert (root / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"original fsr"


def test_control_direct_dll_route_does_not_create_optiscaler_settings(control, dll_catalog):
    service, root = control
    service.install("870780", {"build": "dll-test"})
    assert not (root / "OptiScaler.ini").exists()
    assert not (root / "dxgi.dll").exists()
    service.uninstall("870780")
    assert (root / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"original fsr"
