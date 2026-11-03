import os

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
