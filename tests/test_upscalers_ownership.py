import os
from pathlib import Path

from upscalers import ownership


def test_never_follows_a_link_out_of_the_folder(tmp_path, monkeypatch):
    game, outside = tmp_path / "game", tmp_path / "etc"
    (game / ".pdc-upscaler").mkdir(parents=True)
    outside.mkdir()
    (outside / "shadow").write_text("x")
    (game / ".pdc-upscaler" / "evil").symlink_to(outside, target_is_directory=True)
    (game / ".pdc-upscaler" / "manifest.json").write_text("{}")
    owned = []
    monkeypatch.setattr(ownership.os, "geteuid", lambda: 0)
    monkeypatch.setattr(ownership.os, "chown", lambda path, uid, gid, follow_symlinks=True: owned.append(str(path)))
    ownership.own_like(game, [game / ".pdc-upscaler"])
    assert str(game / ".pdc-upscaler" / "manifest.json") in owned
    assert not any("shadow" in p or p.endswith("evil") for p in owned)


def test_new_launcher_config_takes_its_folders_owner(tmp_path, monkeypatch):
    user = tmp_path / "home"
    (user / "Heroic/GamesConfig").mkdir(parents=True)
    config = user / "Heroic/GamesConfig/game.json"
    config.write_text("{}")
    real_stat = os.stat
    owned = []

    monkeypatch.setattr(ownership.os, "geteuid", lambda: 0)
    monkeypatch.setattr(ownership.os, "chown", lambda path, uid, gid, follow_symlinks=True: owned.append((str(path), uid)))
    def fake_lstat(p, *args, **kwargs):
        stat = real_stat(p, follow_symlinks=False)
        return os.stat_result((stat.st_mode, stat.st_ino, stat.st_dev, stat.st_nlink,
                               0 if Path(p).name == "GamesConfig" else 1000,
                               0 if Path(p).name == "GamesConfig" else 1000, stat.st_size,
                               stat.st_atime, stat.st_mtime, stat.st_ctime))

    monkeypatch.setattr(ownership.os, "lstat", fake_lstat)
    ownership.own_like_ancestor(config)
    assert owned == [(str(config), 1000), (str(user / "Heroic/GamesConfig"), 1000)]


def test_a_linked_folder_on_the_way_stops_everything(tmp_path, monkeypatch):
    user, outside = tmp_path / "home", tmp_path / "etc"
    (user / "Heroic").mkdir(parents=True)
    outside.mkdir()
    (user / "Heroic/GamesConfig").symlink_to(outside, target_is_directory=True)
    config = user / "Heroic/GamesConfig/game.json"
    config.write_text("{}")
    owned = []
    monkeypatch.setattr(ownership.os, "geteuid", lambda: 0)
    monkeypatch.setattr(ownership.os, "chown", lambda *a, **k: owned.append(a[0]))
    ownership.own_like_ancestor(config)
    assert owned == []
