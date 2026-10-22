import base64

import pytest

from accessories.jsaux_pixel import runtime


def test_runtime_is_off_outside_the_steam_machine(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_deck_oled", log=lambda *a, **k: None)
    state = rt.state()
    assert state["supported"] is False
    assert state["present"] is False
    rt.start()
    assert rt.worker is None


def test_catalog_lists_every_scene_with_category_and_label(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None)
    catalog = rt.state()["catalog"]
    ids = [scene["id"] for scene in catalog]
    assert {"fw_tunnel", "fw_dodecahedron", "fw_fireworks", "fw_desert"} <= set(ids)
    assert len(ids) == len(set(ids))
    assert all(scene["category"] and scene["labelKey"].startswith("accessories.scene.") for scene in catalog)


def test_preview_returns_decodable_frames(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None)
    fw = rt.preview("fw_fireworks", {})
    assert fw["firmwareAnimation"] == 2
    for scene in rt.state()["catalog"]:
        preview = rt.preview(scene["id"], {})
        for frame in preview["frames"]:
            assert len(base64.b64decode(frame)) == 64 * 54
        assert len(preview["frames"]) == len(preview["delays"]) <= runtime.PREVIEW_MAX_FRAMES


def test_unknown_scene_raises(tmp_path):
    rt = runtime.Runtime(settings_dir=tmp_path, device_key="steam_machine", log=lambda *a, **k: None,
                         find_panel=lambda: None)
    with pytest.raises(ValueError):
        rt.set_scene("nope", {})
