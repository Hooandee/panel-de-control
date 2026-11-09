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


def test_archives_with_escaping_paths_are_refused(tmp_path):
    archive = _zip(tmp_path / "bad.zip", {"../PDPerfPlugin.dll": b"MZ"})
    assert user_deps.inspect(PLUGIN, archive)["reason"] == "unsafe_archive"


def test_store_keeps_the_choice_and_hands_out_the_files(tmp_path):
    store = user_deps.Store(tmp_path / "store")
    assert store.status(PLUGIN)["state"] == "missing"
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
    assert service.user_file_candidates("puredark-upscaler-base")[0]["version"] == "1.1.2"
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
