from desktop.mode import effective_desktop_mode, migrate_desktop_defaults
from device_registry import detect
from device_profiles import DEVICE_TABLE


FREMONT = next(profile for profile in DEVICE_TABLE if profile.key == "steam_machine")


def test_fremont_enables_desktop_mode_automatically():
    assert effective_desktop_mode(FREMONT, False) is True


def test_generic_linux_requires_manual_opt_in():
    generic = detect(product_name="Unknown Linux PC")
    assert effective_desktop_mode(generic, False) is False
    assert effective_desktop_mode(generic, True) is True


def test_recognised_handheld_cannot_inherit_stale_manual_desktop_opt_in():
    deck = detect(product_name="Galileo")
    assert deck.is_generic is False
    assert effective_desktop_mode(deck, True) is False


def test_recognised_handheld_restores_settings_from_stale_generic_opt_in():
    settings = {
        "desktop_mode_enabled": True,
        "desktop_power_mode": "performance",
        "desktop_prev_tdp_control": True,
        "tdp_control_enabled": False,
    }

    changed = migrate_desktop_defaults(settings, detect(product_name="Galileo"))

    assert changed is True
    assert settings["desktop_mode_enabled"] is False
    assert settings["desktop_power_mode"] == "free"
    assert settings["desktop_prev_tdp_control"] is None
    assert settings["tdp_control_enabled"] is True


def test_recognised_handheld_preserves_stale_opt_in_until_power_handoff_is_restored():
    handoff = {
        "version": 1,
        "boot_id": "boot-1",
        "device_key": "generic",
        "baseline": {"cpu_w": 28, "cpu_policy": None, "gpu_uw": 95_000_000},
    }
    settings = {
        "desktop_mode_enabled": True,
        "desktop_power_mode": "custom",
        "desktop_prev_tdp_control": True,
        "tdp_control_enabled": False,
        "desktop_power_handoff": handoff,
    }

    changed = migrate_desktop_defaults(settings, detect(product_name="Galileo"))

    assert changed is False
    assert settings["desktop_mode_enabled"] is True
    assert settings["desktop_power_mode"] == "custom"
    assert settings["tdp_control_enabled"] is False
    assert settings["desktop_power_handoff"] == handoff


def test_first_fremont_migration_is_free_and_disables_apu_tdp_control():
    settings = {
        "_desktop_defaults_migrated": False,
        "desktop_mode_enabled": False,
        "desktop_power_mode": "balanced",
        "tdp_control_enabled": True,
    }
    changed = migrate_desktop_defaults(settings, FREMONT)
    assert changed is True
    assert settings["desktop_power_mode"] == "free"
    assert settings["tdp_control_enabled"] is False
    assert settings["_desktop_defaults_migrated"] is True


def test_migration_never_changes_other_devices():
    settings = {
        "_desktop_defaults_migrated": False,
        "desktop_power_mode": "balanced",
        "tdp_control_enabled": True,
    }
    changed = migrate_desktop_defaults(settings, detect(product_name="Galileo"))
    assert changed is False
    assert settings["tdp_control_enabled"] is True


def test_migration_does_not_clobber_a_returning_fremont_user():
    settings = {
        "_desktop_defaults_migrated": True,
        "desktop_power_mode": "performance",
        "tdp_control_enabled": True,
    }
    changed = migrate_desktop_defaults(settings, FREMONT)
    assert changed is False
    assert settings["desktop_power_mode"] == "performance"
