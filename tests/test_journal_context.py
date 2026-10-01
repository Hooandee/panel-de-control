import json

from journal_context import (
    StateWatcher,
    active_services,
    context_changes,
    context_snapshot,
    plugin_inventory,
)


def _plugin(root, folder, name, version="1.0.0"):
    path = root / folder
    path.mkdir()
    (path / "plugin.json").write_text(json.dumps({"name": name}))
    (path / "package.json").write_text(json.dumps({"version": version}))


def test_inventory_marks_plugins_decky_has_disabled(tmp_path):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _plugin(plugins, "pdc", "Panel de Control", "0.58.3")
    _plugin(plugins, "sdtdp", "SimpleDeckyTDP", "0.7.0")
    loader = tmp_path / "loader.json"
    loader.write_text(json.dumps({"disabled_plugins": ["SimpleDeckyTDP"]}))
    assert plugin_inventory(str(plugins), str(loader)) == [
        {"name": "Panel de Control", "version": "0.58.3", "enabled": True},
        {"name": "SimpleDeckyTDP", "version": "0.7.0", "enabled": False},
    ]


def test_only_enabled_competitors_and_power_services_are_rivals(tmp_path):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    _plugin(plugins, "a", "PowerTools")
    _plugin(plugins, "b", "SimpleDeckyTDP")
    _plugin(plugins, "c", "SteamGridDB")
    loader = tmp_path / "loader.json"
    loader.write_text(json.dumps({"disabled_plugins": ["SimpleDeckyTDP"]}))
    units = (
        "hhd@deck.service loaded active running Handheld Daemon\n"
        "inputplumber.service loaded active running InputPlumber\n"
        "sshd.service loaded active running OpenSSH\n"
    )
    context = context_snapshot(str(plugins), str(loader), lambda command: units)
    assert context["services"] == ["hhd", "inputplumber"]
    assert context["rivals"] == [
        {"name": "PowerTools", "kind": "plugin", "writes": "tdp"},
        {"name": "hhd", "kind": "service", "writes": "tdp"},
    ]


def test_services_survive_a_failed_systemctl():
    assert active_services(lambda command: None) == []


def test_context_changes_lists_only_what_moved():
    before = {"plugins": [{"name": "A", "version": "1", "enabled": True}], "services": ["hhd"]}
    after = {
        "plugins": [{"name": "A", "version": "1", "enabled": False}, {"name": "B", "version": "2", "enabled": True}],
        "services": [],
    }
    assert context_changes(None, after) is None
    assert context_changes(before, before) is None
    assert context_changes(before, after) == {"added": ["B"], "toggled": ["A"], "services_stopped": ["hhd"]}


def _sample(**overrides):
    sample = {"game": 1, "ac": False, "tdp_w": 15, "control": "in_sync", "w": 14.0, "cpu_c": 70, "gpu_c": 65, "gpu_busy": 99}
    sample.update(overrides)
    return sample


def test_state_is_written_only_when_something_meaningful_moves():
    watcher = StateWatcher(heartbeat_s=1800)
    reasons = [
        watcher.observe(_sample(), 0),
        watcher.observe(_sample(w=13.0, cpu_c=72), 30),
        watcher.observe(_sample(tdp_w=7), 60),
        watcher.observe(_sample(tdp_w=7, ac=True), 90),
        watcher.observe(_sample(tdp_w=7, ac=True, game=None), 120),
        watcher.observe(_sample(tdp_w=7, ac=True, game=None), 2000),
    ]
    assert reasons == ["start", None, "tdp", "power_source", "game", "heartbeat"]


def test_small_tdp_steps_wait_until_they_add_up():
    watcher = StateWatcher()
    watcher.observe(_sample(tdp_w=15), 0)
    assert watcher.observe(_sample(tdp_w=16), 30) is None
    assert watcher.observe(_sample(tdp_w=17), 60) == "tdp"


def test_temperature_bands_have_hysteresis():
    watcher = StateWatcher()
    watcher.observe(_sample(cpu_c=70), 0)
    assert watcher.observe(_sample(cpu_c=91), 30) == "temperature"
    assert watcher.observe(_sample(cpu_c=89), 60) is None
    assert watcher.observe(_sample(cpu_c=86), 90) == "temperature"


def test_low_draw_needs_two_samples_and_reports_its_end():
    watcher = StateWatcher()
    watcher.observe(_sample(tdp_w=30, w=28), 0)
    assert watcher.observe(_sample(tdp_w=30, w=8), 30) is None
    assert watcher.observe(_sample(tdp_w=30, w=8), 60) == "low_draw"
    assert watcher.observe(_sample(tdp_w=30, w=9), 90) is None
    assert watcher.observe(_sample(tdp_w=30, w=27), 120) == "draw_recovered"


def test_a_light_game_with_an_idle_gpu_is_not_a_low_draw():
    watcher = StateWatcher()
    watcher.observe(_sample(tdp_w=15, w=5, gpu_busy=30), 0)
    assert watcher.observe(_sample(tdp_w=15, w=5, gpu_busy=30), 30) is None
    assert watcher.observe(_sample(tdp_w=15, w=5, gpu_busy=35), 60) is None
