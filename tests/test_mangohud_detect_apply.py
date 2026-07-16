from mangohud import apply
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


def test_reload_uses_discovered_mangohud_control_tool(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Result", (), {"returncode": 0})()

    tools = {
        "mangohudctl": "/usr/local/bin/mangohudctl",
        "mangoapp": "/usr/local/bin/mangoapp",
    }
    monkeypatch.setattr(apply.shutil, "which", lambda name, **kwargs: tools.get(name))
    monkeypatch.setattr(apply, "_mangoapp_cwd", lambda: "/home/deck", raising=False)
    monkeypatch.setattr(apply.subprocess, "run", run)

    assert apply.reload_mangoapp() is True
    assert calls[0][0] == ["/usr/local/bin/mangohudctl", "set", "reload_config", "true"]
    assert calls[0][1]["timeout"] == 2
    assert calls[0][1]["cwd"] == "/home/deck"


def test_reload_failure_is_non_fatal(monkeypatch):
    def run(command, **kwargs):
        raise OSError("missing")

    monkeypatch.setattr(apply.shutil, "which", lambda *a, **k: "/usr/bin/mangohudctl")
    monkeypatch.setattr(apply.subprocess, "run", run)

    assert apply.reload_mangoapp() is False


def test_reload_without_control_tool_is_non_fatal(monkeypatch):
    monkeypatch.setattr(apply.shutil, "which", lambda *a, **k: None)

    assert apply.reload_mangoapp() is False


def test_reload_searches_service_path(monkeypatch):
    monkeypatch.setenv("PATH", "/opt/mangohud/bin")

    def which(name, *, path):
        if "/opt/mangohud/bin" not in path:
            return None
        return f"/opt/mangohud/bin/{name}"

    monkeypatch.setattr(apply.shutil, "which", which)
    monkeypatch.setattr(
        apply.subprocess,
        "run",
        lambda *a, **k: type("Result", (), {"returncode": 0})(),
    )

    assert apply.reload_mangoapp() is True
