from kiosk.steam_game import art_file, game_name


def _steam(tmp_path):
    root = tmp_path / ".local/share/Steam"
    (root / "steamapps").mkdir(parents=True)
    return root


def test_reads_the_game_name_from_any_library(tmp_path):
    root = _steam(tmp_path)
    sd = tmp_path / "sdcard"
    (sd / "steamapps").mkdir(parents=True)
    (root / "steamapps/libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n "0" { "path" "%s" }\n "1" { "path" "%s" }\n}\n' % (root, sd)
    )
    (sd / "steamapps/appmanifest_413150.acf").write_text('"AppState"\n{\n "appid" "413150"\n "name" "Stardew Valley"\n}\n')
    assert game_name(str(tmp_path), "413150") == "Stardew Valley"
    assert game_name(str(tmp_path), "999") is None
    assert game_name(str(tmp_path), "../etc") is None


def test_finds_artwork_directly_or_in_hashed_cache_folders(tmp_path):
    root = _steam(tmp_path)
    cache = root / "appcache/librarycache"
    (cache / "413150").mkdir(parents=True)
    (cache / "413150/library_hero.jpg").write_bytes(b"hero")
    (cache / "1625450/a1b2").mkdir(parents=True)
    (cache / "1625450/a1b2/logo.png").write_bytes(b"logo")

    assert art_file(str(tmp_path), "413150", "hero") == (str(cache / "413150/library_hero.jpg"), "image/jpeg")
    assert art_file(str(tmp_path), "1625450", "logo") == (str(cache / "1625450/a1b2/logo.png"), "image/png")
    assert art_file(str(tmp_path), "413150", "logo") is None


def test_rejects_anything_but_known_art_for_numeric_appids(tmp_path):
    _steam(tmp_path)
    assert art_file(str(tmp_path), "../../etc", "hero") is None
    assert art_file(str(tmp_path), "413150", "passwd") is None
