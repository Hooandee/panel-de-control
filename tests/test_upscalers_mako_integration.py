import asyncio
import json
import sys

import pytest

from test_tdp_guard_rpc import plugin
from test_upscalers import APPID, _service, steam, fake_catalog, proc
from upscalers import mako
from upscalers.service import UpscalerError


class FakeMako:
    def status(self):
        return {"installed": True, "ready": True}

    def install(self, cache):
        return self.status()

    def set_game(self, appid, name, config, exe=None):
        return {"env": {"MAKO": "private-command"}, "wrappers": ["private-wrapper"], "profile": config}

    def runtime(self, appid):
        return {"observed": False, "active": False}

    def report(self):
        return {"installed": True, "profiles": {}, "runtime": {}}


def test_service_mako_result_and_report_are_separate(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.mako = FakeMako()
    assert service.mako_status()["ready"]
    assert service.mako_install()["installed"]
    assert service.mako_game(APPID, {"multiplier": 3})["profile"] == {"multiplier": 3}
    assert service.mako_runtime(APPID) == {"observed": False, "active": False}
    service.set_launch_receipt(APPID, "mako", {"version": 1,
        "env": [{"name": "CUSTOM", "before": "private-secret", "applied": "private-command"}],
        "wrappers": {"before": [], "applied": ["private-wrapper"], "added": ["private-wrapper"]}})
    report = service.report()
    assert report["mako"] == service.mako.report()
    assert "private-" not in json.dumps(report)
    assert service.get_launch_receipt(APPID, "mako")["env"][0]["before"] == "private-secret"


def test_mako_errors_are_stable_without_details(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    class Failed(FakeMako):
        def set_game(self, *args):
            raise mako.MakoError("mako_dll_incompatible")
    service.mako = Failed()
    with pytest.raises(UpscalerError, match="mako_dll_incompatible"):
        service.mako_game(APPID, {})
    with pytest.raises(UpscalerError, match="not_installed"):
        service.mako_game("missing", {})


def test_mako_rpc_tracks_safe_actions_and_never_receipt_values(plugin, monkeypatch):
    class Service(FakeMako):
        def __init__(self):
            self.events = []
        def record_action(self, *args):
            self.events.append(args)
        mako_game = FakeMako.set_game
        def set_launch_receipt(self, *args):
            return True
    service = Service()
    service.mako_game = lambda appid, config: {"env": {"SECRET": "private"}, "wrappers": [], "profile": config}
    monkeypatch.setattr(plugin, "_init", lambda: None)
    monkeypatch.setattr(plugin, "_upscalers", lambda: service)
    events = []
    monkeypatch.setattr(sys.modules["main"], "_upscalers_journal", lambda *args, **kw: events.append(kw))
    asyncio.run(plugin.set_mako_game("42", {"multiplier": 3, "env": "secret-command"}))
    assert service.events == [("42", "mako_game", "started", {"multiplier": 3}),
                              ("42", "mako_game", "done", {"multiplier": 3})]
    asyncio.run(plugin.set_upscaler_launch_receipt("42", "mako", {"secret": "private"}))
    assert len(service.events) == 2
    assert "secret" not in json.dumps(events)
    assert "private" not in json.dumps(events)


def test_mako_requested_and_applied_are_distinct_from_runtime(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    class Configured(FakeMako):
        def status(self):
            return {"profiles": {APPID: {"mode": "fixed", "multiplier": 2, "target_fps": 60, "max_multiplier": 3}}}
    service.mako = Configured()
    requested = {"mode": "adaptive", "target_fps": 90, "max_multiplier": 4, "env": "private-command"}
    service.record_action(APPID, "mako_game", "started", requested)
    event = service.report()["games"][0]["actions"][-1]
    assert event["requested"] == {"mode": "adaptive", "target_fps": 90, "max_multiplier": 4}
    assert event["applied_mako"] == {"enabled": True, "mode": "fixed", "multiplier": 2, "target_fps": 60, "max_multiplier": 3}
    assert service.mako_runtime(APPID)["active"] is False
    assert "private-command" not in json.dumps(service.report())


def test_support_state_has_applied_mako_without_runtime_scan(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    class Configured(FakeMako):
        def status(self):
            return {"installed": True, "ready": False, "reason": "mako_unchecked",
                    "profiles": {APPID: {"enabled": True, "mode": "fixed", "multiplier": 3}},
                    "extra": "private-command"}
        def runtime(self, appid):
            raise AssertionError("support state must not scan processes")
        def report(self):
            raise AssertionError("support state must not generate a report")
    service.mako = Configured()
    snapshot = service.support_state()
    assert snapshot["mako"] == {"installed": True, "ready": False, "reason": "mako_unchecked",
                                "profiles": {APPID: {"enabled": True, "mode": "fixed", "multiplier": 3}}}
    assert "private-command" not in json.dumps(snapshot)


class StoredMako(FakeMako):
    def __init__(self):
        self.profiles = {}
    def status(self):
        return {"profiles": dict(self.profiles)}
    def set_game(self, appid, name, config, exe=None):
        self.profiles[appid] = config
        return {"profile": config}
    def runtime(self, appid):
        return {"requested": self.profiles.get(appid), "active": False}


def test_shortcut_identity_survives_alias_but_isolates_paths(steam, fake_catalog, proc, monkeypatch, tmp_path):
    from upscalers.games import Installed
    service = _service(steam, fake_catalog, proc)
    service.mako = StoredMako()
    installed = {"111": Installed("111", "Same name", tmp_path / "one", 4, "game.exe", True, True)}
    monkeypatch.setattr(service, "_find", installed.get)
    receipt = {"version": 1, "env": [], "wrappers": {"before": [], "applied": [], "added": []}}
    service.mako_game("111", {"multiplier": 3})
    service.set_launch_receipt("111", "mako", receipt)
    key = next(iter(service.mako.profiles))
    assert key.isdecimal() and len(key) <= 20
    assert key != "111"
    installed.clear()
    installed["222"] = Installed("222", "Renamed", tmp_path / "one", 4, "game.exe", True, True)
    assert service.mako_status("222")["profiles"] == {"222": {"multiplier": 3}}
    assert service.mako_runtime("222")["requested"] == {"multiplier": 3}
    assert service.get_launch_receipt("222", "mako") == receipt
    installed["333"] = Installed("333", "Renamed", tmp_path / "two", 4, "game.exe", True, True)
    assert service.mako_runtime("333")["requested"] is None
    assert service.get_launch_receipt("333", "mako") is None
    assert not service.state["games"].get("222", {}).get("launch_identity")
    service.mako_game("222", {"multiplier": 3})
    service.record_action("222", "mako_game", "done")
    assert service.state["games"]["222"]["actions"][-1]["applied_mako"]["multiplier"] == 3
    assert service._load()["games"]["222"]["launch_identity"]


def test_live_duplicate_shortcut_cannot_claim_receipt(steam, fake_catalog, proc, monkeypatch, tmp_path):
    from upscalers.games import Installed
    service = _service(steam, fake_catalog, proc)
    service.mako = StoredMako()
    installed = {key: Installed(key, "Duplicate", tmp_path, 4, "game.exe", True, True) for key in ("111", "222")}
    monkeypatch.setattr(service, "_find", installed.get)
    service.mako_game("111", {"multiplier": 3})
    assert service.mako_status("222") == {"profiles": {}, "ready": False, "reason": "mako_identity_ambiguous",
                                          "scaler_transition_pending": False}
    assert "222" not in service.state["games"]
    for call in (lambda: service.mako_game("222", None), lambda: service.mako_game("222", {}),
                 lambda: service.get_launch_receipt("222", "mako")):
        with pytest.raises(UpscalerError, match="mako_identity_ambiguous"):
            call()


def test_steam_and_unresolved_receipt_keys_stay_unchanged(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.mako = StoredMako()
    service.mako_game(APPID, {"multiplier": 2})
    assert service.mako_status(APPID)["profiles"] == {APPID: {"multiplier": 2}}
    assert service._launch_owner(APPID) == APPID
    assert service._launch_owner("missing") == "missing"
