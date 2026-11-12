import hashlib
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from test_upscalers import APPID, FakeHelix, without_bundled_recipes, _service, _write, dll_catalog, fake_catalog, helix_catalog, proc, steam
from upscalers import catalog, diagnostics, games, recipes
from upscalers.catalog import Asset


@pytest.mark.parametrize("marker", [False, True])
def test_reframework_requirement_composes_with_other_files(tmp_path, marker):
    if marker:
        _write(tmp_path / recipes.RE_ENGINE_MARKER)
    base = recipes.Recipe("1", files={"helper.dll": "helper"}, needs=("reframework", "mod"),
                          native_dlls=("helper",))
    result = recipes.with_engine(base, "1", tmp_path)
    assert result.files == {"helper.dll": "helper", "dinput8.dll": "reframework-nightly"}
    assert result.native_dlls == ("helper", "dinput8")
    assert result.needs == ("mod",)
    assert result.menu_key == "home"
    assert base.files == {"helper.dll": "helper"}


def test_existing_specific_reframework_is_preserved_and_overrides_deduplicated(tmp_path):
    _write(tmp_path / recipes.RE_ENGINE_MARKER)
    base = recipes.Recipe("1", files={"DINPUT8.DLL": "specific", "helper.dll": "helper"},
                          native_dlls=("DINPUT8", "dinput8", "helper"), needs=("reframework", "mod"))
    result = recipes.with_engine(base, "1", tmp_path)
    assert result.files == base.files
    assert result.native_dlls == ("DINPUT8", "helper")
    assert result.needs == ("mod",)
    assert recipes.with_engine(result, "1", tmp_path) == result


@pytest.fixture
def re_catalog(dll_catalog, monkeypatch):
    payload = b"official framework"
    asset = Asset("reframework-nightly", "REFramework.zip", hashlib.sha256(payload).hexdigest(), len(payload),
                  ("http://invalid",), member="dinput8.dll")
    monkeypatch.setitem(catalog.ASSETS, asset.id, asset)
    _write(Path(dll_catalog) / "cache" / asset.sha256 / "unpacked/dinput8.dll", payload)
    monkeypatch.setitem(recipes.RECIPES, APPID, recipes.Recipe(APPID, needs=("reframework",)))
    return dll_catalog


def test_applied_components_survive_catalog_changes_and_optiscaler_to_dll_restore(steam, re_catalog, proc, monkeypatch):
    _, game = steam
    target = game / "bin/x64_dx12"
    original = _write(target / "dinput8.dll", b"original loader")
    service = _service(steam, re_catalog, proc)
    result = service.install(APPID, {"build": "fsr-test"})
    assert "dinput8=n,b" in result["overrides"]
    assert original.read_bytes() == b"official framework"
    expected = [{"id": asset.id, "sha256": asset.sha256} for asset in catalog.build_assets(catalog.BUILDS["fsr-test"])]
    expected.append({"id": "reframework-nightly", "sha256": catalog.ASSETS["reframework-nightly"].sha256})
    assert [{key: item[key] for key in ("id", "sha256")} for item in service.game(APPID)["install"]["components"]] == expected
    monkeypatch.setitem(catalog.ASSETS, "reframework-nightly", replace(catalog.ASSETS["reframework-nightly"], sha256="0" * 64))
    reloaded = _service(steam, re_catalog, proc)
    stored = service.game(APPID)["install"]["components"]
    assert stored[0]["source"] == "pinned" and stored[0]["fallback"] == "unresolved" and stored[-1].get("source") == "pinned", stored
    reported = [{**item, "sha256": "-".join(item["sha256"][index:index + 4] for index in range(0, 64, 4))}
                for item in stored]
    assert reloaded.diagnose(APPID)["current"]["applied"]["components"] == reported
    reloaded.install(APPID, {"build": "dll-test"})
    assert original.read_bytes() == b"original loader"
    report = reloaded.diagnose(APPID)
    assert report["previous"]["applied"]["components"] == reported
    assert report["current"]["applied"]["components"] == []
    assert report["install"]["native_dlls"] == []
    reloaded.uninstall(APPID)
    assert original.read_bytes() == b"original loader"
    assert (target / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"x"


def test_recipe_copy_failure_restores_originals_without_applied_components(steam, re_catalog, proc, monkeypatch):
    _, game = steam
    target = game / "bin/x64_dx12"
    original = _write(target / "dinput8.dll", b"original loader")
    service = _service(steam, re_catalog, proc)
    copyfile = shutil.copyfile

    def failing_copy(source, destination, *args, **kwargs):
        if Path(destination) == original:
            raise OSError("copy failed")
        return copyfile(source, destination, *args, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", failing_copy)
    with pytest.raises(OSError, match="copy failed"):
        service.install(APPID, {"build": "fsr-test"})
    assert original.read_bytes() == b"original loader"
    assert (target / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"x"
    assert not (target / games.MANIFEST_DIR).exists()
    assert service.game(APPID)["install"] is None


def test_component_report_bounds_and_rejects_paths_urls_and_invalid_hashes():
    valid = {"id": "reframework-nightly", "sha256": "a" * 64, "url": "private", "path": "/home/private"}
    values = [{"id": "/home/private", "sha256": "a" * 64}, {"id": "rf", "sha256": "not a hash"}, valid] + [valid] * 80
    report = diagnostics.snapshot({"engine": "dll", "components": values})
    components = report["applied"]["components"]
    assert len(components) <= 32
    assert components and all(item == {"id": "reframework-nightly", "sha256": "-".join(["aaaa"] * 16)} for item in components)
    assert diagnostics.snapshot({"engine": "dll", "components": "invalid"})["applied"]["components"] == []


@pytest.mark.parametrize("build", ["dll-test", "hlx-fsr4"])
def test_non_optiscaler_routes_do_not_fetch_or_apply_reframework(steam, re_catalog, helix_catalog, proc, monkeypatch, build):
    _, game = steam
    _write(game / recipes.RE_ENGINE_MARKER)
    target = game / "bin/x64_dx12"
    original = _write(target / "dinput8.dll", b"other loader")
    service = _service(steam, re_catalog, proc)
    service.helix = FakeHelix()
    ensure = service.cache.ensure

    def only_route_assets(asset, *args):
        assert asset.id != "reframework-nightly"
        return ensure(asset, *args)

    monkeypatch.setattr(service.cache, "ensure", only_route_assets)
    result = service.install(APPID, {"build": build})
    assert result["overrides"] == []
    assert original.read_bytes() == b"other loader"
    assert service.diagnose(APPID)["current"]["applied"]["components"] == []
    service.uninstall(APPID)
    assert original.read_bytes() == b"other loader"


def test_real_asset_digest_survives_current_and_previous_report_redaction():
    from copy import deepcopy
    from pdc_report.collector import redact_obj

    asset = catalog.ASSETS["reframework-nightly"]
    install = {"engine": "dll", "components": [{"id": asset.id, "sha256": asset.sha256}]}
    before = deepcopy(install)
    previous = diagnostics.snapshot(install)
    report = redact_obj({"current": diagnostics.snapshot(install), "previous": previous})
    expected = "-".join(asset.sha256[index:index + 4] for index in range(0, 64, 4))
    assert report["current"]["applied"]["components"] == [{"id": asset.id, "sha256": expected}]
    assert report["previous"]["applied"]["components"] == report["current"]["applied"]["components"]
    assert redact_obj(report) == report
    assert expected.replace("-", "") == asset.sha256
    assert install == before


@pytest.fixture
def unknown_game_service(steam, fake_catalog, proc, monkeypatch):
    without_bundled_recipes(monkeypatch)
    monkeypatch.setattr(recipes, "RECIPES", {})
    monkeypatch.setattr(recipes, "WIKI", {})
    service = _service(steam, fake_catalog, proc)
    assert not service.wiki.path.exists()
    assert not service.wiki.pages_path.exists()
    assert service.wiki.lookup("Witcher") is None
    assert service.game(APPID)["recipe_info"] is None
    return service


def _run_bounded_job(service, operation, *args):
    from threading import Thread

    identifier = service.begin(operation.__name__, APPID)
    worker = Thread(target=service.run, args=(operation, APPID, *args), daemon=True)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive(), "job did not finish within the local fixture deadline"
    job = service.job()
    assert job["id"] == identifier
    assert job["state"] != "running"
    return job


def test_unknown_game_generic_install_finishes_and_accepts_following_jobs(steam, unknown_game_service):
    _, game = steam
    target = game / "bin/x64_dx12"
    service = unknown_game_service
    installed = _run_bounded_job(service, service.install, {"build": "fsr-test"})
    assert installed["state"] == "done"
    assert (target / "dxgi.dll").read_bytes() == b"injector"
    assert installed["result"]["args"] == []
    assert installed["result"]["overrides"] == ["dxgi=n,b"]
    assert not (target / "dinput8.dll").exists()
    removed = _run_bounded_job(service, service.uninstall)
    assert removed["state"] == "done"
    assert not (target / "dxgi.dll").exists()
    assert (target / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"x"
    retried = _run_bounded_job(service, service.install, {"build": "fsr-test"})
    assert retried["state"] == "done"
    assert len({installed["id"], removed["id"], retried["id"]}) == 3
    assert _run_bounded_job(service, service.uninstall)["state"] == "done"


def test_unknown_game_download_timeout_finishes_and_can_retry(steam, unknown_game_service, monkeypatch):
    from upscalers.assets import AssetError

    _, game = steam
    target = game / "bin/x64_dx12"
    service = unknown_game_service
    ensure = service.cache.ensure

    def timed_out(asset, *args):
        raise AssetError("download_failed", "TimeoutError")

    monkeypatch.setattr(service.cache, "ensure", timed_out)
    failed = _run_bounded_job(service, service.install, {"build": "fsr-test"})
    assert failed["state"] == "error"
    assert failed["error"] == "download_failed"
    assert service.game(APPID)["install"] is None
    assert (target / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == b"x"
    assert not (target / "dxgi.dll").exists()
    monkeypatch.setattr(service.cache, "ensure", ensure)
    retried = _run_bounded_job(service, service.install, {"build": "fsr-test"})
    assert retried["id"] != failed["id"]
    assert retried["state"] == "done"
    assert (target / "dxgi.dll").read_bytes() == b"injector"
    assert _run_bounded_job(service, service.uninstall)["state"] == "done"


def test_reframework_starts_with_its_menu_closed_and_leaves_nothing_behind(steam, re_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    service = _service(steam, re_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    config = target / "re2_fw_config.txt"
    assert "REFrameworkConfig_MenuOpen=false" in config.read_text()
    assert "REFrameworkConfig_RememberMenuState=true" in config.read_text()
    config.write_text("REFrameworkConfig_MenuOpen=false\nREFrameworkConfig_FontSize=16\n")
    service.uninstall(APPID)
    assert not config.exists()
    assert not (target / games.MANIFEST_DIR).exists()


def test_an_existing_reframework_config_keeps_its_settings_and_gets_its_keys_back(steam, re_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    config = _write(target / "re2_fw_config.txt", b"REFrameworkConfig_FontSize=20\nREFrameworkConfig_RememberMenuState=false\n")
    service = _service(steam, re_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    text = config.read_text()
    assert "REFrameworkConfig_FontSize=20" in text
    assert "REFrameworkConfig_RememberMenuState=true" in text and "REFrameworkConfig_MenuOpen=false" in text
    config.write_text(text + "REFrameworkConfig_UIFontSize=1.5\n")
    service.uninstall(APPID)
    restored = config.read_text()
    assert "REFrameworkConfig_RememberMenuState=false" in restored and "MenuOpen" not in restored
    assert "REFrameworkConfig_FontSize=20" in restored and "REFrameworkConfig_UIFontSize=1.5" in restored
    assert not (target / games.MANIFEST_DIR).exists()


def test_an_untouched_existing_reframework_config_comes_back_exactly(steam, re_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    config = _write(target / "re2_fw_config.txt", b"REFrameworkConfig_MenuOpen=true\n")
    service = _service(steam, re_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    service.uninstall(APPID)
    assert config.read_bytes() == b"REFrameworkConfig_MenuOpen=true\n"
