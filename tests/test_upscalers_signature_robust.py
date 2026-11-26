import json
from dataclasses import replace
from pathlib import Path

import pytest

from test_upscalers import APPID, _service, _write, fake_catalog, proc, steam  # noqa: F401
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


def test_eac_makes_the_signed_build_preferred_where_one_is_supported():
    plain = catalog.preferred_build("rdna2")
    signed = catalog.preferred_build("rdna2", prefer_signed=True)
    assert plain == "fsr-4.1.2-beta" and catalog.build_signed(catalog.BUILDS[signed]) and signed != plain


def test_required_signed_matches_the_curated_recipe_choice_on_rdna2():
    assert catalog.preferred_build("rdna2", require_signed=True) == "fsr-4.1.1"


def test_measured_signature_wins_over_the_declared_one():
    build = catalog.BUILDS["fsr-3.1"]
    assert catalog.build_signed(build)
    for asset_id in (build.archive, *build.assets):
        asset = catalog.ASSETS[asset_id]
        catalog.record_signature(asset.id, asset.sha256, False)
    assert not catalog.build_signed(build)


def test_a_failed_build_is_skipped_and_signed_ones_come_first():
    assert catalog.preferred_build("rdna2", failed={"fsr-4.1.2-beta"}) != "fsr-4.1.2-beta"
    assert catalog.build_signed(catalog.BUILDS[catalog.preferred_build("rdna2", failed={"fsr-4.1.2-beta"})])


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
    return {"appid": appid, "start": "launch", "seconds": seconds, "outcome": "short" if seconds < 90 else "normal",
            "injections": {engine: {"build": build}}}


def installed_service(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
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
