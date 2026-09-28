import os
import types

from desktop.board_fans import BoardFanDriver, available_modules

RELEASE = "7.2.3-test"


def _w(path, value=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(value)


def _ship(root, *names):
    for name in names:
        _w(os.path.join(root, "lib/modules", RELEASE, "kernel/drivers/hwmon", f"{name}.ko.zst"))


def _board_chip(root, name="nct6798"):
    d = os.path.join(root, "sys/class/hwmon/hwmon5")
    _w(os.path.join(d, "name"), name)
    for leaf, value in (("pwm1", "100"), ("pwm1_enable", "5"), ("fan1_input", "800")):
        _w(os.path.join(d, leaf), value)


class FakeModprobe:
    def __init__(self, root, binds=()):
        self.root = root
        self.binds = set(binds)
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        name = argv[-1]
        if argv[1] == "-r":
            return types.SimpleNamespace(returncode=0)
        os.makedirs(os.path.join(self.root, "sys/module", name), exist_ok=True)
        if name in self.binds:
            _board_chip(self.root)
        return types.SimpleNamespace(returncode=0)


def _driver(root, run):
    return BoardFanDriver(root=str(root), run=run, release=RELEASE, settle_s=0)


def test_only_shipped_candidates_are_offered(tmp_path):
    _ship(str(tmp_path), "it87", "nct6775")
    assert available_modules(str(tmp_path), RELEASE) == ["nct6775", "it87"]


def test_load_stops_at_the_first_driver_that_exposes_fans_and_unloads_the_rest(tmp_path):
    _ship(str(tmp_path), "nct6775", "nct6683", "it87")
    run = FakeModprobe(str(tmp_path), binds={"nct6683"})

    state = _driver(tmp_path, run).load()

    assert run.calls == [["modprobe", "nct6775"], ["modprobe", "-r", "nct6775"],
                         ["modprobe", "nct6683"]]
    assert state["channels"] == 1
    assert state["loaded_by_panel"] == ["nct6683"]
    assert state["last"]["ok"] is True


def test_no_board_fans_is_reported_honestly(tmp_path):
    _ship(str(tmp_path), "nct6775")
    run = FakeModprobe(str(tmp_path))

    state = _driver(tmp_path, run).load()

    assert state["channels"] == 0
    assert state["loaded_by_panel"] == []
    assert state["last"] == {"action": "load", "ok": False, "channels": 0,
                             "attempts": [{"module": "nct6775", "result": "no_fans"}],
                             "detail": "no_board_fans"}


def test_failed_modprobe_is_recorded_and_never_retried_with_overrides(tmp_path):
    _ship(str(tmp_path), "it87")

    def refuse(argv):
        return types.SimpleNamespace(returncode=1)

    state = _driver(tmp_path, refuse).load()
    assert state["last"]["attempts"] == [{"module": "it87", "result": "exit_1"}]


def test_unload_removes_only_what_the_panel_loaded(tmp_path):
    _ship(str(tmp_path), "nct6775")
    os.makedirs(os.path.join(str(tmp_path), "sys/module/it87"))
    run = FakeModprobe(str(tmp_path), binds={"nct6775"})
    driver = _driver(tmp_path, run)
    driver.load()

    driver.unload()

    assert run.calls[-1] == ["modprobe", "-r", "nct6775"]
    assert all("it87" not in call for call in run.calls)


def _plugin(monkeypatch, channels_after_load):
    import asyncio  # noqa: F401
    import sys
    if "decky" not in sys.modules:
        decky = types.ModuleType("decky")
        decky.DECKY_PLUGIN_SETTINGS_DIR = "/tmp"
        decky.DECKY_USER_HOME = "/tmp"
        decky.DECKY_USER = "deck"
        decky.logger = types.SimpleNamespace(info=lambda *a, **k: None,
                                             warning=lambda *a, **k: None,
                                             error=lambda *a, **k: None)
        sys.modules["decky"] = decky
    import main
    from device_profiles import DESKTOP_PC

    class Driver:
        def __init__(self):
            self.calls = []

        def state(self):
            return {"available": ["nct6775"], "loaded": [], "loaded_by_panel": [],
                    "channels": channels_after_load if self.calls[-1:] == ["load"] else 0,
                    "last": None}

        active_module = "nct6775"

        def load(self, only=None):
            self.calls.append("load")
            return self.state()

        def unload(self):
            self.calls.append("unload")
            return self.state()

    class Ctrl:
        name = "null"
        released = 0

        def restore_auto(self):
            Ctrl.released += 1
            return {"ok": True}

    plugin = main.Plugin.__new__(main.Plugin)
    plugin._init = lambda: None
    plugin._device = DESKTOP_PC
    plugin._settings = {"board_fan_driver": False, "fan_experimental": False}
    plugin._board_fans = Driver()
    plugin._fan_ctrl = Ctrl()
    plugin._save = lambda: None
    plugin._reapply_fans_sync = lambda: True
    plugin._ensure_fan_loop = lambda: None
    plugin._driving_temp = lambda: 50.0

    async def offload(fn):
        return fn()

    plugin._offload_call = offload
    monkeypatch.setattr(main.fan_control, "select_fan_backend", lambda *a, **k: Ctrl())
    return plugin


def test_opt_in_persists_only_when_board_fans_appear(monkeypatch):
    import asyncio
    plugin = _plugin(monkeypatch, channels_after_load=0)
    state = asyncio.run(plugin.set_board_fan_enabled(True))
    assert plugin._settings["board_fan_driver"] is False
    assert state["enabled"] is False

    plugin = _plugin(monkeypatch, channels_after_load=3)
    asyncio.run(plugin.set_board_fan_enabled(True))
    assert plugin._settings["board_fan_driver"] is True
    assert plugin._settings["board_fan_module"] == "nct6775"
    assert plugin._board_fans.calls == ["load"]


def test_opt_out_releases_fans_before_unloading(monkeypatch):
    import asyncio
    plugin = _plugin(monkeypatch, channels_after_load=3)
    plugin._settings["board_fan_driver"] = True
    before = type(plugin._fan_ctrl).released

    asyncio.run(plugin.set_board_fan_enabled(False))

    assert type(plugin._fan_ctrl).released == before + 1
    assert plugin._board_fans.calls == ["unload"]
    assert plugin._settings["board_fan_driver"] is False


def test_handhelds_have_no_board_fan_driver(monkeypatch):
    import asyncio
    plugin = _plugin(monkeypatch, channels_after_load=3)
    plugin._board_fans = None
    assert asyncio.run(plugin.set_board_fan_enabled(True)) == {"supported": False}


def test_restart_reloads_only_the_driver_that_worked(tmp_path):
    _ship(str(tmp_path), "nct6775", "it87")
    run = FakeModprobe(str(tmp_path), binds={"it87"})

    _driver(tmp_path, run).load(only="it87")

    assert run.calls == [["modprobe", "it87"]]
