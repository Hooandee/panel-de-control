import os
import zipfile

import pytest

from upscalers import user_deps
from upscalers.recipe_catalog import DependencySpec

PLUGIN = DependencySpec("puredark", "user_files", None, {"PDPerfPlugin.dll": "PDPerfPlugin.dll"}, None, None, (),
                        "UpscalerBasePlugin", "https://www.nexusmods.com/site/mods/502", "1.1.2", ("1.2.0",))


def _zip(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def test_finds_the_plugin_anywhere_in_a_nexus_archive_and_reads_its_version(tmp_path):
    archive = _zip(tmp_path / "UpscalerBasePlugin-502-1-1-2-1700000000.zip",
                   {"UpscalerBasePlugin/PDPerfPlugin.dll": b"MZplugin", "readme.txt": b"x"})
    found = user_deps.inspect(PLUGIN, archive)
    assert found == {"ok": True, "reason": None, "version": "1.1.2", "filename": archive.name}


def test_a_loose_dll_counts_and_a_wrong_archive_says_what_is_missing(tmp_path):
    dll = tmp_path / "PDPerfPlugin.dll"
    dll.write_bytes(b"MZplugin")
    assert user_deps.inspect(PLUGIN, dll)["ok"] is True
    other = _zip(tmp_path / "Something-1.0.zip", {"other.dll": b"MZ"})
    assert user_deps.inspect(PLUGIN, other)["reason"] == "missing_files"
    assert user_deps.inspect(PLUGIN, tmp_path / "nope.zip")["reason"] == "unreadable"


@pytest.mark.parametrize("member", ["../PDPerfPlugin.dll", "-T/etc/PDPerfPlugin.dll", "a/--x/PDPerfPlugin.dll"])
def test_archives_with_escaping_or_option_like_paths_are_refused(tmp_path, member):
    archive = _zip(tmp_path / "bad.zip", {member: b"MZ"})
    assert user_deps.inspect(PLUGIN, archive)["reason"] == "unsafe_archive"


def test_archive_paths_with_brackets_are_taken_literally(tmp_path):
    import tarfile
    source = tmp_path / "PDPerfPlugin.dll"
    source.write_bytes(b"MZplugin")
    archive = tmp_path / "UpscalerBasePlugin-502-1-1-2-1.7z"  # bsdtar reads the format from the content
    with tarfile.open(archive, "w") as tar:
        tar.add(source, arcname="Plugin [1.1.2]/PDPerfPlugin.dll")
    store = user_deps.Store(tmp_path / "store")
    assert store.adopt(PLUGIN, archive)["state"] == "ready"
    assert store.sources(PLUGIN)["PDPerfPlugin.dll"].read_bytes() == b"MZplugin"


def test_a_loose_dll_saved_in_other_case_is_stored_under_the_wanted_name(tmp_path):
    dll = tmp_path / "pdperfplugin.dll"
    dll.write_bytes(b"MZplugin")
    store = user_deps.Store(tmp_path / "store")
    assert store.adopt(PLUGIN, dll)["state"] == "ready"
    assert store.sources(PLUGIN)["PDPerfPlugin.dll"].name == "PDPerfPlugin.dll"


def test_candidates_inspect_each_download_once_until_it_changes(tmp_path, monkeypatch):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    archive = _zip(downloads / "UpscalerBasePlugin-502-1-1-2-1.zip", {"PDPerfPlugin.dll": b"MZ"})
    calls = []
    real = user_deps.inspect
    monkeypatch.setattr(user_deps, "inspect", lambda dep, path: calls.append(path) or real(dep, path))
    user_deps.candidates(PLUGIN, [downloads])
    user_deps.candidates(PLUGIN, [downloads])
    assert len(calls) == 1
    os.utime(archive, ns=(1, 1))
    user_deps.candidates(PLUGIN, [downloads])
    assert len(calls) == 2


def test_store_keeps_the_choice_and_hands_out_the_files(tmp_path):
    store = user_deps.Store(tmp_path / "store")
    assert store.status(PLUGIN)["state"] == "missing"
    assert store.status(PLUGIN)["download_url"] == PLUGIN.page_url
    assert store.sources(PLUGIN) == {}
    archive = _zip(tmp_path / "UpscalerBasePlugin-502-1-2-0-1700000000.zip", {"x/PDPerfPlugin.dll": b"MZnew"})
    status = store.adopt(PLUGIN, archive)
    assert status["state"] == "avoid" and status["installed_version"] == "1.2.0"
    archive.unlink()
    source = store.sources(PLUGIN)["PDPerfPlugin.dll"]
    assert source.read_bytes() == b"MZnew"
    good = _zip(tmp_path / "UpscalerBasePlugin-502-1-1-2-1700000000.zip", {"PDPerfPlugin.dll": b"MZgood"})
    assert store.adopt(PLUGIN, good)["state"] == "ready"
    assert store.sources(PLUGIN)["PDPerfPlugin.dll"].read_bytes() == b"MZgood"
    store.remove(PLUGIN)
    assert store.status(PLUGIN)["state"] == "missing"


def test_adopting_a_wrong_file_keeps_the_previous_choice(tmp_path):
    store = user_deps.Store(tmp_path / "store")
    store.adopt(PLUGIN, _zip(tmp_path / "a-1.1.2.zip", {"PDPerfPlugin.dll": b"MZ"}))
    with pytest.raises(user_deps.UserFileError) as error:
        store.adopt(PLUGIN, _zip(tmp_path / "b.zip", {"other.dll": b"MZ"}))
    assert error.value.code == "missing_files"
    assert store.status(PLUGIN)["state"] == "ready"


def test_candidates_are_the_matching_downloads_newest_first(tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    old = _zip(downloads / "UpscalerBasePlugin-502-1-1-2-1.zip", {"PDPerfPlugin.dll": b"MZ"})
    new = _zip(downloads / "UpscalerBasePlugin-502-1-2-0-2.zip", {"PDPerfPlugin.dll": b"MZ"})
    _zip(downloads / "unrelated.zip", {"a.dll": b"MZ"})
    (downloads / "notes.txt").write_text("x")
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))
    found = user_deps.candidates(PLUGIN, [downloads, tmp_path / "missing"])
    assert [c["filename"] for c in found] == [new.name, old.name]
    assert found[0]["version"] == "1.2.0" and found[0]["path"] == str(new)


def test_service_adopts_only_files_under_home_and_names_the_problem(tmp_path, monkeypatch):
    from upscalers import service as service_module
    from upscalers.service import UpscalerError, UpscalerService
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    service = UpscalerService(str(home), str(tmp_path / "state"), "rdna3", proc=str(tmp_path))
    monkeypatch.setattr(service, "game", lambda appid: {"appid": appid})
    good = _zip(home / "Downloads" / "UpscalerBasePlugin-502-1-1-2-1.zip", {"PDPerfPlugin.dll": b"MZ"})
    found = service.user_file_candidates("puredark-upscaler-base")
    assert found["folder"] == str(home / "Downloads") and found["candidates"][0]["version"] == "1.1.2"
    assert service.add_user_file("2050650", "puredark-upscaler-base", str(good)) == {"appid": "2050650"}
    dependency = service_module.recipe_catalog.bundled().dependencies["puredark-upscaler-base"]
    assert service.user_files.status(dependency)["state"] == "ready"
    wrong = _zip(home / "Downloads" / "other.zip", {"a.dll": b"MZ"})
    outside = _zip(tmp_path / "outside.zip", {"PDPerfPlugin.dll": b"MZ"})
    for path, code in ((wrong, "user_file_wrong"), (outside, "user_file_unreadable")):
        with pytest.raises(UpscalerError) as error:
            service.add_user_file("2050650", "puredark-upscaler-base", str(path))
        assert error.value.code == code
    with pytest.raises(UpscalerError):
        service.add_user_file("2050650", "refw-pdup-re4", str(good))
    service.remove_user_file("2050650", "puredark-upscaler-base")
    assert service.user_files.status(dependency)["state"] == "missing"


def test_game_detail_lists_user_files_and_does_not_claim_luma(tmp_path, monkeypatch):
    from upscalers import auto_recipes, recipe_catalog, recipes
    from upscalers.service import UpscalerService
    import test_upscalers
    home = tmp_path / "home"
    game_root = home / ".local/share/Steam/steamapps/common/Witcher"
    test_upscalers._write(home / ".local/share/Steam/steamapps/libraryfolders.vdf",
                          '"libraryfolders"\n{\n "0"\n {\n  "path" "%s"\n }\n}\n' % (home / ".local/share/Steam"))
    test_upscalers._write(home / f".local/share/Steam/steamapps/appmanifest_{test_upscalers.APPID}.acf",
                          '"AppState"\n{\n "appid" "%s"\n "name" "Witcher"\n "installdir" "Witcher"\n "StateFlags" "4"\n}\n' % test_upscalers.APPID)
    test_upscalers._write(game_root / "re4.exe", b"MZ" + b"\0" * 64)
    service = UpscalerService(str(home), str(tmp_path / "state"), "rdna3", proc=str(tmp_path))
    curated = recipe_catalog.bundled().match("2050650", "optiscaler", "linux", "x86_64")
    monkeypatch.setattr(service, "_recipe", lambda *a: recipes.recipe_for("2050650", platform="linux", arch="x86_64"))
    monkeypatch.setattr(auto_recipes, "plan", lambda recipe, installed: curated)
    info = service.game(test_upscalers.APPID)["recipe_info"]
    assert info["automatic"] == []
    assert [(f["id"], f["state"]) for f in info["user_files"]] == [("puredark-upscaler-base", "missing")]


def test_fps_counter_is_unavailable_with_optiscalers_old_menu():
    from upscalers import recipes
    from upscalers.service import _recipe_info
    assert _recipe_info(recipes.Recipe("1"))["fps_counter"] is True
    assert _recipe_info(recipes.Recipe("1", ini={"Menu.OverlayMenu": "false"}))["fps_counter"] is False
    assert _recipe_info(recipes.Recipe("1", wiki_settings={"OverlayMenu": "false"}))["fps_counter"] is False
    assert _recipe_info(recipes.Recipe("1", ini={"Menu.OverlayMenu": "true"}, reframework_upscaler=True))["fps_counter"] is False
    assert _recipe_info(recipes.recipe_for("2050650", platform="linux", arch="x86_64"))["fps_counter"] is False
