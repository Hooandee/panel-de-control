import sys
import types


if "decky" not in sys.modules:
    decky = types.ModuleType("decky")
    decky.DECKY_PLUGIN_SETTINGS_DIR = "/tmp"
    decky.DECKY_USER = "deck"
    decky.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    sys.modules["decky"] = decky

import main
from tdp.types import TdpLimits


class _Store:
    def __init__(self):
        self.saves = 0

    def save(self, settings):
        self.saves += 1


class _FailingStore(_Store):
    def save(self, settings):
        super().save(settings)
        raise OSError("disk full")


class _Result:
    def __init__(self, ok, reason=None):
        self.ok = ok
        self.reason = reason


class _DeckBackend:
    name = "steamdeck-hwmon"
    primary_rail = "pl2"

    def __init__(self, restore_ok=True):
        self.restore_ok = restore_ok
        self.capture_calls = 0
        self.restore_calls = []
        self.snapshot = {"slow": 14, "fast": 16}

    def ppt_capability(self):
        return {"supported": True}

    def capture_ppt(self):
        self.capture_calls += 1
        return dict(self.snapshot)

    def configured_tdp_ceiling(self, snapshot=None):
        baseline = self.snapshot if snapshot is None else snapshot
        slow = baseline.get("slow") if isinstance(baseline, dict) else None
        return slow if isinstance(slow, int) and slow > 15 else None

    def get_limits(self):
        return TdpLimits(3, 12, 15, 15)

    def level_limits(self):
        return {
            "pl2": {"min": 3, "max": 29},
            "pl3": {"min": 3, "max": 30},
        }

    def physical_levels(self, levels):
        return {"pl2": int(levels["pl2"]), "pl3": int(levels["pl3"])}

    def validate_ppt_snapshot(self, snapshot):
        return (
            isinstance(snapshot, dict)
            and isinstance(snapshot.get("slow"), int)
            and isinstance(snapshot.get("fast"), int)
            and 0 <= snapshot["slow"] <= 29
            and 0 <= snapshot["fast"] <= 30
            and snapshot["slow"] <= snapshot["fast"]
        )

    def restore_ppt(self, snapshot):
        self.restore_calls.append(dict(snapshot))
        return _Result(self.restore_ok, None if self.restore_ok else "write_fast")


def _plugin(backend):
    plugin = main.Plugin.__new__(main.Plugin)
    plugin._tdp_backend = backend
    plugin._settings = {"steamdeck_ppt_previous": None}
    plugin._store = _Store()
    plugin._tdp_history = []
    return plugin


class _Profiles:
    def __init__(self, pl1):
        self._pl1 = pl1

    def effective(self, _appid):
        return {
            "pl1": self._pl1,
            "pl2": self._pl1,
            "pl3": self._pl1,
            "watts": self._pl1,
            "mode": "estable",
        }


def _with_limits(plugin, pl1):
    plugin._device = types.SimpleNamespace(
        key="steam_deck_oled",
        charger_only_extra=False,
        cooler_max=None,
        experimental_tdp_max_ac=None,
        tdp_max_charger=15,
    )
    plugin._settings.update({
        "unlock_battery_max": False,
        "cooler_boost": False,
        "experimental_tdp_unlock": False,
        "eco_enabled": False,
    })
    plugin._tdp_profiles = _Profiles(pl1)
    return plugin


def _command(mode):
    return types.SimpleNamespace(
        logical_requested={"pl1": 15, "pl2": 29, "pl3": 30, "mode": mode},
        requested={"pl2": 29, "pl3": 30} if mode != "estable" else {"pl2": 15, "pl3": 15},
    )


def test_first_advanced_apply_persists_snapshot_before_takeover():
    backend = _DeckBackend()
    plugin = _plugin(backend)

    assert plugin._prepare_steamdeck_ppt(_command("custom")) is None

    assert plugin._settings["steamdeck_ppt_previous"] == {"slow": 14, "fast": 16}
    assert backend.capture_calls == 1
    assert plugin._store.saves == 1


def test_later_advanced_apply_does_not_replace_original_snapshot():
    backend = _DeckBackend()
    plugin = _plugin(backend)
    plugin._settings["steamdeck_ppt_previous"] = {"slow": 13, "fast": 15}

    assert plugin._prepare_steamdeck_ppt(_command("auto")) is None

    assert backend.capture_calls == 0
    assert plugin._settings["steamdeck_ppt_previous"] == {"slow": 13, "fast": 15}


def test_saved_overclock_baseline_sets_the_automatic_ceiling_while_owned():
    backend = _DeckBackend()
    plugin = _with_limits(_plugin(backend), pl1=25)
    plugin._settings["steamdeck_ppt_previous"] = {"slow": 25, "fast": 30}

    assert plugin._steamdeck_overclock_state() == {
        "detected": True,
        "max_w": 25,
        "source": "handoff",
    }
    assert plugin._automatic_limits() == TdpLimits(3, 12, 25, 25)
    assert plugin._effective_levels(None, on_ac=True)[0]["pl1"] == 25
    assert plugin._preset_wclamp() == (3, 25)


def test_stock_live_ppt_keeps_automatic_tdp_at_fifteen_watts():
    backend = _DeckBackend()
    backend.snapshot = {"slow": 15, "fast": 30}
    plugin = _with_limits(_plugin(backend), pl1=25)

    assert plugin._steamdeck_overclock_state() == {
        "detected": False,
        "max_w": None,
        "source": "live",
    }
    assert plugin._automatic_limits() == TdpLimits(3, 12, 15, 15)
    assert plugin._effective_levels(None, on_ac=True)[0]["pl1"] == 15


def test_stable_keeps_slow_and_fast_owned_until_power_handoff():
    backend = _DeckBackend()
    plugin = _plugin(backend)
    plugin._settings["steamdeck_ppt_previous"] = {"slow": 13, "fast": 15}

    assert plugin._prepare_steamdeck_ppt(_command("estable")) is None

    assert backend.restore_calls == []
    assert plugin._settings["steamdeck_ppt_previous"] == {"slow": 13, "fast": 15}

    plugin._settings["hhd_tdp_prev"] = None
    assert plugin._restore_power_handoff() is True
    assert backend.restore_calls == [{"slow": 13, "fast": 15}]
    assert plugin._settings["steamdeck_ppt_previous"] is None


def test_failed_release_keeps_marker_and_blocks_handoff():
    backend = _DeckBackend(restore_ok=False)
    plugin = _plugin(backend)
    marker = {"slow": 13, "fast": 15}
    plugin._settings["steamdeck_ppt_previous"] = marker
    plugin._settings["hhd_tdp_prev"] = None

    released = plugin._restore_power_handoff()

    assert released is False
    assert plugin._settings["steamdeck_ppt_previous"] == marker
    assert plugin._restore_steamdeck_ppt() is False


def test_restored_hardware_keeps_retry_marker_when_persistence_fails():
    backend = _DeckBackend()
    plugin = _plugin(backend)
    plugin._store = _FailingStore()
    marker = {"slow": 13, "fast": 15}
    plugin._settings["steamdeck_ppt_previous"] = marker

    assert plugin._restore_steamdeck_ppt() is False

    assert backend.restore_calls == [marker]
    assert plugin._settings["steamdeck_ppt_previous"] == marker
    assert plugin._steamdeck_ppt_recovery_blocked is True
    assert plugin._steamdeck_ppt_last_failure["reason"] == "persist_OSError"


def test_emergency_restore_keeps_snapshot_for_a_late_ppt_write():
    backend = _DeckBackend()
    plugin = _plugin(backend)
    marker = {"slow": 13, "fast": 15}
    plugin._settings["steamdeck_ppt_previous"] = marker

    emergency = plugin._restore_steamdeck_ppt(preserve_ownership=True)

    assert emergency is True
    assert plugin._settings["steamdeck_ppt_previous"] == marker

    final = plugin._restore_steamdeck_ppt()

    assert final is True
    assert backend.restore_calls == [marker, marker]
    assert plugin._settings["steamdeck_ppt_previous"] is None


def test_takeover_does_not_start_when_snapshot_persistence_fails():
    backend = _DeckBackend()
    plugin = _plugin(backend)
    plugin._store = _FailingStore()

    assert plugin._prepare_steamdeck_ppt(_command("custom")) == "snapshot_persist_OSError"

    assert plugin._settings["steamdeck_ppt_previous"] is None
    assert plugin._steamdeck_ppt_recovery_blocked is True


def test_takeover_rejects_snapshot_that_cannot_be_restored():
    backend = _DeckBackend()
    backend.snapshot = {"slow": 35, "fast": 40}
    plugin = _plugin(backend)

    assert plugin._prepare_steamdeck_ppt(_command("custom")) == "snapshot_invalid"

    assert plugin._settings["steamdeck_ppt_previous"] is None
    assert plugin._store.saves == 0
