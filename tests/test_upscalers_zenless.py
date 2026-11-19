import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from upscalers import UpscalerError, catalog, recipe_catalog
from test_upscalers import _service, _write, proc


APPID = "4162040"
BUILD = "fsr-4.1.2-lite-dll"
EXE = "games/ZenlessZoneZero Game/ZenlessZoneZero.exe"
PROVIDER = "amd_fidelityfx_upscaler_dx12.dll"


@pytest.fixture
def zenless(tmp_path, monkeypatch):
    monkeypatch.setattr(recipe_catalog.host_platform, "system", lambda: "Linux")
    monkeypatch.setattr(recipe_catalog.host_platform, "machine", lambda: "x86_64")
    home = tmp_path / "player home"
    steam = home / ".local/share/Steam"
    library = tmp_path / "SD Card Steam Library"
    _write(steam / "steamapps/libraryfolders.vdf", f'"libraryfolders" {{ "0" {{ "path" "{library}" }} }}')
    _write(library / f"steamapps/appmanifest_{APPID}.acf",
           f'"AppState" {{ "appid" "{APPID}" "name" "Zenless Zone Zero" "installdir" "Zenless Zone Zero" "StateFlags" "4" }}')
    game = library / "steamapps/common/Zenless Zone Zero"
    _write(game / "HYP.exe")
    _write(game / EXE, b"MZ" + b"\0" * 64)
    return home, game


def test_steam_lite_recommendation_requires_the_game_provider(zenless, proc, tmp_path):
    _, game = zenless
    target = game / EXE
    service = _service(zenless, tmp_path / "state", proc)
    assert service.game(APPID)["preferred"] != BUILD

    _write(game / "another-folder" / PROVIDER)
    assert service.compatibility([APPID])[APPID]["preferred"] != BUILD

    _write(target.with_name(PROVIDER))
    assert service.game(APPID)["preferred"] == BUILD
    assert service.game(APPID)["recipe_info"]["automatic_builds"] == [BUILD]
    compatibility = service.compatibility([APPID])[APPID]
    assert compatibility["preferred"] == BUILD
    assert "FSR 3.1" in compatibility["inputs"]

    service.set_exe(APPID, "HYP.exe")
    assert service.game(APPID)["analysis"]["exe"] == "HYP.exe"
    assert service.game(APPID)["preferred"] != BUILD
    assert service.compatibility([APPID])[APPID]["preferred"] != BUILD

    service.set_exe(APPID, None)
    service.gpu = "rdna3"
    assert service.game(APPID)["preferred"] != BUILD


def test_managed_lite_install_changes_only_the_game_provider_and_launch_argv(zenless, proc, tmp_path, monkeypatch):
    _, game = zenless
    target = game / EXE
    provider = _write(target.with_name(PROVIDER), "original provider")
    files = {
        _write(target.with_name("amd_fidelityfx_loader_dx12.dll"), "loader"): "loader",
        _write(target.with_name("amd_fidelityfx_framegeneration_dx12.dll"), "frame generation"): "frame generation",
        _write(target.with_name("HoYoKProtect.sys"), "security driver"): "security driver",
        _write(game / "another-folder" / "amd_fidelityfx_dx12.dll", "other provider"): "other provider",
    }
    service = _service(zenless, tmp_path / "state", proc)
    asset_id = catalog.BUILDS[BUILD].replace[PROVIDER]
    payload = _write(tmp_path / "download" / PROVIDER, "lite provider")
    monkeypatch.setattr(service.cache, "ensure", lambda asset, *_: {asset_id: payload}[asset.id])
    request = {"build": BUILD, "confirm_anti_cheat": True}
    with pytest.raises(UpscalerError, match="recipe_transaction_required"):
        service.install(APPID, request)
    assert provider.read_text() == "original provider"

    checkpoint = service.begin_scaler_transition(APPID)
    result = service.install(APPID, request)
    service.finish_scaler_transition(APPID, checkpoint["token"])

    assert provider.read_text() == "lite provider"
    assert all(path.read_text() == data for path, data in files.items())
    assert result["files"] == 1
    assert result["overrides"] == []
    assert service.game(APPID)["install"]["exe"] == EXE
    assert service.verify(APPID)["result"] == "not_run"

    options = " ".join(f"{name}={value}" for name, value in result["env"].items())
    command = [
        sys.executable, "-c", "import json, os, sys; print(json.dumps([os.getcwd(), sys.argv[1:]]))",
        "waitforexitandrun", str(game / "HYP.exe"), "-arg", "keep spaces", f"--other={game / 'HYP.exe'}",
    ]
    launch = f"{options} {' '.join(result['wrappers'])} {shlex.join(command)}"
    run = subprocess.run(["bash", "-c", launch], cwd=game, check=True, text=True, capture_output=True)
    cwd, args = json.loads(run.stdout)
    assert Path(cwd).resolve() == game.resolve()
    assert args == ["waitforexitandrun", str(target), "-arg", "keep spaces", f"--other={game / 'HYP.exe'}", "-use-d3d12"]

    for launcher, expected in (("HYP.exe", EXE), ("otherHYP.exe", "otherHYP.exe")):
        command[4] = launcher
        launch = f"{options} {' '.join(result['wrappers'])} {shlex.join(command)}"
        run = subprocess.run(["bash", "-c", launch], cwd=game, check=True, text=True, capture_output=True)
        _, args = json.loads(run.stdout)
        assert args[1] == expected
        assert ("-use-d3d12" in args) == (launcher == "HYP.exe")

    checkpoint = service.begin_scaler_transition(APPID)
    restore = service.finish_scaler_transition(APPID, checkpoint["token"], rollback=True)
    assert restore["wrappers"] == result["wrappers"]
    assert restore["env"] == result["env"]
    service.finish_scaler_transition(APPID, checkpoint["token"])

    service.uninstall(APPID)
    assert provider.read_text() == "original provider"
    assert all(path.read_text() == data for path, data in files.items())


def test_explicit_executable_selection_stays_on_the_generic_dll_path(zenless, proc, tmp_path, monkeypatch):
    _, game = zenless
    _write((game / EXE).with_name(PROVIDER))
    service = _service(zenless, tmp_path / "state", proc)
    asset_id = catalog.BUILDS[BUILD].replace[PROVIDER]
    payload = _write(tmp_path / "download" / PROVIDER)
    monkeypatch.setattr(service.cache, "ensure", lambda asset, *_: {asset_id: payload}[asset.id])
    service.set_exe(APPID, "HYP.exe")
    result = service.install(APPID, {"build": BUILD})
    assert not result.get("wrappers")
    assert service.game(APPID)["install"]["exe"] == "HYP.exe"
