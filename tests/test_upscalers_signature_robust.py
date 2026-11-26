import json
import time
from dataclasses import replace
from pathlib import Path

import pytest

from test_upscalers import APPID, _service, _write, dll_catalog, fake_catalog, proc, steam  # noqa: F401
from test_upscalers_pe_sign import make_pe
from upscalers import catalog, games
from upscalers.catalog import Asset, Build
from upscalers.service import UpscalerError


@pytest.fixture(autouse=True)
def clean_measurements():
    catalog.MEASURED.clear()
    yield
    catalog.MEASURED.clear()


def game_tree(tmp_path, *marks):
    root = tmp_path / "Diablo IV"
    _write(root / "Diablo IV.exe", b"MZ" + b"\0" * 4096)
    for mark in marks:
        _write(root / mark)
    return root


def test_diablo_iv_tree_with_blizzard_error_is_signed_only_without_a_recipe(tmp_path):
    analysis = games.analyze(game_tree(tmp_path, "BlizzardError/ReportedBugs/x.dmp"))
    assert analysis["anti_cheat"] and analysis["anti_cheat_kind"] == "signed_only"


@pytest.mark.parametrize("mark", ["Battle.net/x.dat", "vgk.sys", "VGK.SYS", "xigncode/x3.xem", "GameGuard/GameMon.des",
                                  "ACE-Base64.dll", "AntiCheatExpert/x.dat", "HoYoKProtect.sys", "mhyprot2.sys", "mhyprot3.sys"])
def test_known_protections_that_kill_unsigned_code(tmp_path, mark):
    assert games.analyze(game_tree(tmp_path, mark))["anti_cheat_kind"] == "signed_only"


@pytest.mark.parametrize("mark", ["Content/Vanguard_Armor.pak", "vgk_shaders.bin", "Battle.net.dll", "Vanguard/x.dat"])
def test_a_name_that_merely_contains_a_protection_is_not_one(tmp_path, mark):
    assert games.analyze(game_tree(tmp_path, mark))["anti_cheat_kind"] is None


def test_easy_anti_cheat_only_warns(tmp_path):
    analysis = games.analyze(game_tree(tmp_path, "EasyAntiCheat/eac.dll"))
    assert analysis["anti_cheat"] and analysis["anti_cheat_kind"] == "warn"


def test_a_game_folder_named_vanguard_is_not_a_protection(tmp_path):
    root = tmp_path / "Call of Duty Vanguard"
    _write(root / "game.exe", b"MZ" + b"\0" * 4096)
    analysis = games.analyze(root)
    assert not analysis["anti_cheat"] and analysis["anti_cheat_kind"] is None


def test_eac_does_not_trade_the_family_for_a_signature():
    assert catalog.preferred_build("rdna2", "steam_deck_lcd", prefer_signed=True) == "fsr-4.1.2-beta"
    assert catalog.preferred_build("rdna2", prefer_signed=True) == "fsr-4.1.2-beta"


def test_a_failed_default_falls_to_another_fsr_not_to_xess():
    assert catalog.preferred_build("rdna3", failed={"fsr-4.1.1"}) == "fsr-4.1.2-beta"
    assert catalog.preferred_build("rdna2", failed={"fsr-4.1.2-beta"}) != "xess"


def test_required_signed_matches_the_curated_recipe_choice_on_rdna2():
    assert catalog.preferred_build("rdna2", require_signed=True) == "fsr-4.1.1"


def test_measured_signature_wins_over_the_declared_one():
    build = catalog.BUILDS["fsr-3.1"]
    assert catalog.build_signed(build)
    for asset_id in (build.archive, *build.assets):
        asset = catalog.ASSETS[asset_id]
        catalog.record_signature(asset.id, asset.sha256, False)
    assert not catalog.build_signed(build)


def test_a_failed_build_is_skipped():
    assert catalog.preferred_build("rdna2", failed={"fsr-4.1.2-beta"}) != "fsr-4.1.2-beta"


@pytest.fixture(autouse=True)
def fake_preferred(request, monkeypatch):
    if "fake_catalog" in request.fixturenames:
        monkeypatch.setattr(catalog, "PREFERRED", {"rdna2": "fsr-test"})


def blizzard_game(steam):
    _, game = steam
    _write(game / "BlizzardError/ReportedBugs/x.dmp")
    return game


def second_signed_build(monkeypatch):
    other = Asset("other-archive", "other.7z", "b" * 64, 1, ("http://invalid",), True, signed=True)
    monkeypatch.setitem(catalog.ASSETS, other.id, other)
    monkeypatch.setitem(catalog.BUILDS, "fsr-other", Build("fsr-other", "fsr", "4.1.0", ("rdna2",), 2, 3, archive=other.id))


def declare_signed(monkeypatch):
    monkeypatch.setitem(catalog.ASSETS, catalog.OPTISCALER_ARCHIVE,
                        replace(catalog.ASSETS[catalog.OPTISCALER_ARCHIVE], signed=True))
    monkeypatch.setitem(catalog.ASSETS, "extra", replace(catalog.ASSETS["extra"], signed=True))


def test_unsigned_optiscaler_dll_refuses_the_install_and_recommends_the_next_signed_build(steam, fake_catalog, proc, monkeypatch):
    game = blizzard_game(steam)
    declare_signed(monkeypatch)
    second_signed_build(monkeypatch)
    unpacked = Path(fake_catalog) / "cache" / catalog.ASSETS[catalog.OPTISCALER_ARCHIVE].sha256 / "unpacked"
    make_pe(unpacked / "OptiScaler.dll", signed=False)
    service = _service(steam, fake_catalog, proc)
    assert service.game(APPID)["preferred"] == "fsr-test"
    with pytest.raises(UpscalerError) as refused:
        service.install(APPID, {"build": "fsr-test", "confirm_anti_cheat": True})
    assert refused.value.code == "unsigned_build" and refused.value.detail == "OptiScaler.dll"
    target = game / "bin/x64_dx12"
    assert not (target / "dxgi.dll").exists() and not (target / "OptiScaler.ini").exists()
    detail = service.game(APPID)
    assert detail["preferred"] == "fsr-other"
    saved = json.loads(service.state_path.read_text())["signatures"]
    assert list(saved.values()) == [{"id": catalog.OPTISCALER_ARCHIVE, "signed": False}]


def test_signed_optiscaler_dll_installs_for_a_signed_only_game(steam, fake_catalog, proc, monkeypatch):
    game = blizzard_game(steam)
    declare_signed(monkeypatch)
    unpacked = Path(fake_catalog) / "cache" / catalog.ASSETS[catalog.OPTISCALER_ARCHIVE].sha256 / "unpacked"
    make_pe(unpacked / "OptiScaler.dll", signed=True)
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test", "confirm_anti_cheat": True})
    assert (game / "bin/x64_dx12/dxgi.dll").is_file()
    assert catalog.build_signed(catalog.BUILDS["fsr-test"])


def test_measurements_survive_a_restart(steam, fake_catalog, proc, monkeypatch):
    blizzard_game(steam)
    declare_signed(monkeypatch)
    unpacked = Path(fake_catalog) / "cache" / catalog.ASSETS[catalog.OPTISCALER_ARCHIVE].sha256 / "unpacked"
    make_pe(unpacked / "OptiScaler.dll", signed=False)
    with pytest.raises(UpscalerError):
        _service(steam, fake_catalog, proc).install(APPID, {"build": "fsr-test", "confirm_anti_cheat": True})
    catalog.MEASURED.clear()
    _service(steam, fake_catalog, proc)
    assert not catalog.build_signed(catalog.BUILDS["fsr-test"])


def launch(appid, build, seconds, engine="optiscaler"):
    return {"appid": appid, "start": "launch", "seconds": seconds, "ended_by": "game_stopped", "outcome": "short" if seconds < 90 else "normal",
            "injections": {engine: {"build": build}}, "process": [{"at": 5, "reaper": True, "processes": 3, "names": ["Game.exe"]}]}


def installed_service(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.mark_delay = 0
    service.install(APPID, {"build": "fsr-test"})
    return service


def test_a_short_launch_with_optiscaler_marks_the_build_and_changes_the_preferred(steam, fake_catalog, proc, monkeypatch):
    second_signed_build(monkeypatch)
    service = installed_service(steam, fake_catalog, proc)
    assert service.game(APPID)["preferred"] == "fsr-test"
    service.session_outcome(launch(APPID, "fsr-test", 88.7))
    detail = service.game(APPID)
    mark = detail["failed_builds"][0]
    assert mark["build"] == "fsr-test" and mark["seconds"] == 88.7 and mark["version"] and "at" in mark
    assert detail["preferred"] == "fsr-other"
    assert json.loads(service.state_path.read_text())["games"][APPID]["failed_builds"]["fsr-test"]["seconds"] == 88.7


def test_a_normal_launch_with_that_build_clears_the_mark(steam, fake_catalog, proc):
    service = installed_service(steam, fake_catalog, proc)
    service.session_outcome(launch(APPID, "fsr-test", 30))
    service.session_outcome(launch(APPID, "fsr-test", 900))
    detail = service.game(APPID)
    assert detail["failed_builds"] == [] and detail["preferred"] == "fsr-test"


def test_installing_the_build_again_clears_the_mark(steam, fake_catalog, proc):
    service = installed_service(steam, fake_catalog, proc)
    service.session_outcome(launch(APPID, "fsr-test", 30))
    service.install(APPID, {"build": "fsr-test"})
    assert service.game(APPID)["failed_builds"] == []


@pytest.mark.parametrize("engine", ["proton", "mako", "lsfg"])
def test_other_injections_are_never_marked(steam, fake_catalog, proc, engine):
    service = installed_service(steam, fake_catalog, proc)
    service.session_outcome(launch(APPID, "proton-fsr4", 20, engine))
    assert service.game(APPID)["failed_builds"] == []


def test_attached_sessions_and_vanilla_launches_are_never_marked(steam, fake_catalog, proc):
    service = installed_service(steam, fake_catalog, proc)
    service.session_outcome({**launch(APPID, "fsr-test", 20), "start": "attached", "outcome": None})
    service.session_outcome({**launch(APPID, "fsr-test", 20), "injections": {}})
    assert service.game(APPID)["failed_builds"] == []


@pytest.mark.parametrize("ended_by", ["context_change", "plugin_unload", None])
def test_only_a_stopped_game_ends_a_session_that_marks_a_build(steam, fake_catalog, proc, ended_by):
    service = installed_service(steam, fake_catalog, proc)
    service.session_outcome({**launch(APPID, "fsr-test", 20), "ended_by": ended_by})
    assert service.game(APPID)["failed_builds"] == []


def test_the_report_carries_failed_builds_without_free_text(steam, fake_catalog, proc):
    service = installed_service(steam, fake_catalog, proc)
    service.session_outcome(launch(APPID, "fsr-test", 20))
    service.state["games"][APPID]["failed_builds"]["fsr-test"]["note"] = "/home/someone/secret"
    report = service.report()
    rows = report["games"][0]["failed_builds"]
    assert rows[0]["build"] == "fsr-test" and "note" not in rows[0] and "someone" not in json.dumps(rows)


def test_a_measurement_of_another_sha_never_stands_in_for_the_asset():
    build = catalog.BUILDS["fsr-3.1"]
    asset = catalog.ASSETS[build.archive]
    catalog.record_signature(asset.id, "f" * 64, False)
    assert catalog.asset_signed(asset) == asset.signed


def test_required_signed_with_no_signed_build_recommends_nothing(monkeypatch):
    monkeypatch.setattr(catalog, "build_signed", lambda build: False)
    assert catalog.preferred_build("rdna2", require_signed=True) == ""
    assert catalog.preferred_build("rdna2") != ""


def package(fake_catalog):
    return Path(fake_catalog) / "cache" / catalog.ASSETS[catalog.OPTISCALER_ARCHIVE].sha256 / "unpacked"


def test_a_signed_only_install_keeps_the_rest_of_the_package_but_never_the_games_own_files(steam, fake_catalog, proc, monkeypatch):
    game = blizzard_game(steam)
    declare_signed(monkeypatch)
    unpacked = package(fake_catalog)
    make_pe(unpacked / "OptiScaler.dll", signed=True)
    make_pe(unpacked / "libxess.dll", signed=True)
    make_pe(unpacked / "amd_fidelityfx_upscaler_dx12.dll", signed=True)
    make_pe(unpacked / "fakenvapi.dll", signed=False)
    make_pe(unpacked / "dlssg_to_fsr3_amd_is_better.dll", signed=False)
    target = game / "bin/x64_dx12"
    ships = _write(target / "amd_fidelityfx_loader_dx12.dll", b"loader")
    own = target / "amd_fidelityfx_upscaler_dx12.dll"
    before = own.read_bytes()
    _service(steam, fake_catalog, proc).install(APPID, {"build": "fsr-test", "confirm_anti_cheat": True})
    assert (target / "libxess.dll").is_file() and (target / "D3D12_Optiscaler/D3D12Core.dll").is_file()
    assert (target / "dxgi.dll").is_file() and (target / "amdxcffx64.dll").is_file()
    assert not (target / "fakenvapi.dll").exists() and not (target / "dlssg_to_fsr3_amd_is_better.dll").exists()
    assert own.read_bytes() == before and ships.read_bytes() == b"loader"


def test_a_signed_only_install_brings_the_packages_ffx_library_to_a_game_without_one(steam, fake_catalog, proc, monkeypatch):
    game = blizzard_game(steam)
    declare_signed(monkeypatch)
    unpacked = package(fake_catalog)
    make_pe(unpacked / "OptiScaler.dll", signed=True)
    make_pe(unpacked / "amd_fidelityfx_upscaler_dx12.dll", signed=True)
    target = game / "bin/x64_dx12"
    (target / "amd_fidelityfx_upscaler_dx12.dll").unlink()
    _service(steam, fake_catalog, proc).install(APPID, {"build": "fsr-test", "confirm_anti_cheat": True})
    assert (target / "amd_fidelityfx_upscaler_dx12.dll").read_bytes() == (unpacked / "amd_fidelityfx_upscaler_dx12.dll").read_bytes()


def test_an_unsigned_library_in_the_package_refuses_a_signed_only_install(steam, fake_catalog, proc, monkeypatch):
    game = blizzard_game(steam)
    declare_signed(monkeypatch)
    unpacked = package(fake_catalog)
    make_pe(unpacked / "OptiScaler.dll", signed=True)
    make_pe(unpacked / "libxess.dll", signed=False)
    with pytest.raises(UpscalerError) as refused:
        _service(steam, fake_catalog, proc).install(APPID, {"build": "fsr-test", "confirm_anti_cheat": True})
    assert refused.value.code == "unsigned_build" and refused.value.detail == "libxess.dll"
    assert not (game / "bin/x64_dx12/dxgi.dll").exists()


def test_a_build_swapped_after_the_old_install_is_measured_too(steam, fake_catalog, proc, monkeypatch):
    game = blizzard_game(steam)
    declare_signed(monkeypatch)
    make_pe(package(fake_catalog) / "OptiScaler.dll", signed=True)
    later = Asset("later-archive", "later.7z", "c" * 64, 1, ("http://invalid",), True, signed=True)
    monkeypatch.setitem(catalog.ASSETS, later.id, later)
    unpacked = Path(fake_catalog) / "cache" / later.sha256 / "unpacked"
    unpacked.mkdir(parents=True)
    make_pe(unpacked / "OptiScaler.dll", signed=False)
    _write(unpacked / "OptiScaler.ini", "[FSR]\n")
    _write(unpacked / ".complete", later.sha256)
    calls = []

    def swap(build, *args):
        calls.append(build.id)
        return build if len(calls) == 1 else replace(build, archive=later.id)

    monkeypatch.setattr(catalog, "for_game", swap)
    with pytest.raises(UpscalerError) as refused:
        _service(steam, fake_catalog, proc).install(APPID, {"build": "fsr-test", "confirm_anti_cheat": True})
    assert refused.value.code == "unsigned_build" and len(calls) >= 2
    assert not (game / "bin/x64_dx12/dxgi.dll").exists()


def test_standalone_dll_builds_are_refused_for_a_signed_only_game(steam, dll_catalog, proc):
    game = blizzard_game(steam)
    original = game / "bin/x64_dx12/amd_fidelityfx_upscaler_dx12.dll"
    before = original.read_bytes()
    with pytest.raises(UpscalerError) as refused:
        _service(steam, dll_catalog, proc).install(APPID, {"build": "dll-test", "confirm_anti_cheat": True})
    assert refused.value.code == "unsigned_build" and original.read_bytes() == before


@pytest.mark.parametrize("probes", ["not_sampled", [], [{"at": 5, "reaper": True, "processes": 2, "names": []}]])
def test_a_short_session_without_the_game_process_never_marks(steam, fake_catalog, proc, probes):
    service = installed_service(steam, fake_catalog, proc)
    service.session_outcome({**launch(APPID, "fsr-test", 20), "process": probes})
    assert service.game(APPID)["failed_builds"] == []


def test_the_mark_waits_and_a_relaunch_inside_the_window_discards_it(steam, fake_catalog, proc):
    service = installed_service(steam, fake_catalog, proc)
    service.mark_delay = 0.2
    service.session_outcome(launch(APPID, "fsr-test", 20))
    assert service.game(APPID)["failed_builds"] == []
    service.session_started(APPID)
    time.sleep(0.5)
    assert service.game(APPID)["failed_builds"] == []


def test_the_mark_lands_when_nothing_relaunches(steam, fake_catalog, proc):
    service = installed_service(steam, fake_catalog, proc)
    service.mark_delay = 0.1
    service.session_outcome(launch(APPID, "fsr-test", 20))
    time.sleep(0.5)
    assert [item["build"] for item in service.game(APPID)["failed_builds"]] == ["fsr-test"]


def test_uninstalling_or_replacing_the_build_forgets_its_mark(steam, fake_catalog, proc):
    service = installed_service(steam, fake_catalog, proc)
    service.session_outcome(launch(APPID, "fsr-test", 20))
    service.uninstall(APPID)
    assert service.game(APPID)["failed_builds"] == []
    service.install(APPID, {"build": "fsr-test"})
    service.session_outcome(launch(APPID, "fsr-test", 20))
    service.state["games"][APPID]["failed_builds"]["other"] = {}
    service._forget_mark(service.state["games"][APPID], {"build": "other"})
    assert "other" not in service.state["games"][APPID]["failed_builds"]
    service.install(APPID, {"build": "fsr-test", "quality": "balanced"})
    assert service.game(APPID)["failed_builds"] == []


def test_state_writes_wait_for_the_state_lock(steam, fake_catalog, proc):
    import threading
    service = installed_service(steam, fake_catalog, proc)
    done = threading.Event()
    with service._state_lock:
        thread = threading.Thread(target=lambda: (service.session_outcome(launch(APPID, "fsr-test", 20)), done.set()))
        thread.start()
        assert not done.wait(0.3)
    assert done.wait(2)


def test_assets_sharing_one_archive_sha_keep_their_own_measurement():
    one = Asset("member-one", "a.dll", "c" * 64, 1, ("http://invalid",), True, signed=True, member="a.dll")
    two = Asset("member-two", "b.dll", "c" * 64, 1, ("http://invalid",), True, signed=True, member="b.dll")
    catalog.record_signature("member-one", "c" * 64, False)
    assert not catalog.asset_signed(one) and catalog.asset_signed(two)
