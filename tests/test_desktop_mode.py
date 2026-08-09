from desktop.mode import effective_desktop_mode, migrate_desktop_defaults
from device_registry import detect


def test_fremont_enables_desktop_mode_automatically():
    assert effective_desktop_mode(detect(product_name="Fremont"), False) is True


def test_generic_linux_requires_manual_opt_in():
    generic = detect(product_name="Unknown Linux PC")
    assert effective_desktop_mode(generic, False) is False
    assert effective_desktop_mode(generic, True) is True


def test_first_fremont_migration_is_free_and_disables_apu_tdp_control():
    settings = {
        "_desktop_defaults_migrated": False,
        "desktop_mode_enabled": False,
        "desktop_power_mode": "balanced",
        "tdp_control_enabled": True,
    }
    changed = migrate_desktop_defaults(settings, detect(product_name="Fremont"))
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
    changed = migrate_desktop_defaults(settings, detect(product_name="Fremont"))
    assert changed is False
    assert settings["desktop_power_mode"] == "performance"
