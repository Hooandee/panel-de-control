from mangohud.apply import apply_hud, clear_presets, read_presets
from mangohud.config import build_presets_conf, coerce_model
from mangohud.detect import presets_path, presets_supported


# ---- detect: pure decision from a process environ ----

def test_presets_supported_flag():
    assert presets_supported({"STEAM_MANGOAPP_PRESETS_SUPPORTED": "1"}) is True
    assert presets_supported({"STEAM_MANGOAPP_PRESETS_SUPPORTED": "0"}) is False
    assert presets_supported({}) is False


def test_presets_path_prefers_explicit_env():
    p = presets_path({"MANGOHUD_PRESETSFILE": "/tmp/custom/presets.conf"}, home="/home/deck")
    assert p == "/tmp/custom/presets.conf"


def test_presets_path_uses_xdg_config_home():
    p = presets_path({"XDG_CONFIG_HOME": "/home/deck/.cfg"}, home="/home/deck")
    assert p == "/home/deck/.cfg/MangoHud/presets.conf"


def test_presets_path_defaults_to_home_config():
    p = presets_path({}, home="/home/deck")
    assert p == "/home/deck/.config/MangoHud/presets.conf"


def test_presets_path_prefers_mangoapp_HOME_over_our_root_home():
    # we run as root (home=/root) but the overlay reads the deck user's config
    p = presets_path({"HOME": "/home/deck"}, home="/root")
    assert p == "/home/deck/.config/MangoHud/presets.conf"


# ---- apply: write presets.conf + honest readback ----

def test_apply_writes_presets_conf_and_reads_it_back(tmp_path):
    path = str(tmp_path / "sub" / "presets.conf")  # parent dir does not exist yet
    model = coerce_model({"metrics": ["fps", "gpu"]})
    on_disk = apply_hud(model, path)
    assert on_disk == build_presets_conf(model)
    assert read_presets(path) == on_disk  # readback = what actually landed


def test_read_presets_missing_returns_none(tmp_path):
    assert read_presets(str(tmp_path / "nope.conf")) is None


def test_clear_presets_removes_our_file_and_is_idempotent(tmp_path):
    path = str(tmp_path / "presets.conf")
    apply_hud(coerce_model({"metrics": ["fps"]}), path)
    assert read_presets(path) is not None
    clear_presets(path)  # hands the overlay back to MangoHud's stock defaults
    assert read_presets(path) is None
    clear_presets(path)  # already gone — must not raise


def test_apply_bakes_pdc_values_into_presets(tmp_path):
    path = str(tmp_path / "presets.conf")
    model = coerce_model({"items": [{"kind": "metric", "id": "pdc_tdp"}], "enabled": True})
    on_disk = apply_hud(model, path, {"pdc_tdp": "21W"})
    assert "custom_text=TDP 21W" in on_disk
    assert "exec=" not in on_disk
