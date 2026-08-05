import pytest

from mangohud import pdc_metrics as pdc


CASES = [
    ("pdc_tdp", {"auto": True, "applied": 18}, None, "Auto 18W"),
    ("pdc_tdp", {"auto": False, "applied": 20}, None, "20W"),
    ("pdc_tdp", {"auto": True, "applied": 18, "eco": True}, None, "Auto 18W"),
    ("pdc_tdp", {"auto": False, "applied": 19.6}, None, "20W"),
    ("pdc_tdp", {"auto": False, "applied": None}, None, "-"),
    ("pdc_tdp", {"auto": True, "applied": None}, None, "Auto -"),
    ("pdc_tdp_learn", {"learn": {"enough": True, "floor": 13, "ceil": 19}}, None, "13-19W"),
    ("pdc_tdp_learn", {}, None, "-"),
    ("pdc_tdp_learn", {"learn": {"reason": "disabled"}}, None, "-"),
    ("pdc_tdp_learn", {"learn": {"reason": "no_game"}}, None, "-"),
    ("pdc_tdp_learn", {"learn": {"reason": "error"}}, None, "-"),
    ("pdc_fan", {"fan_mode": "auto", "fan_confirmed": True}, None, "Auto"),
    ("pdc_fan", {"fan_mode": "custom", "fan_confirmed": True}, None, "Curva"),
    ("pdc_fan", {"fan_mode": "silent", "fan_confirmed": True}, None, "Silencioso"),
    ("pdc_fan", {"fan_mode": "adaptive", "fan_learning": True, "fan_confirmed": True}, None, "Adaptativo (aprendiendo)"),
    ("pdc_fan", {"fan_mode": "adaptive", "fan_learning": False, "fan_confirmed": True}, None, "Adaptativo"),
    ("pdc_fan", {"fan_mode": "???"}, None, "-"),
    ("pdc_fan", {"fan_mode": "performance", "fan_confirmed": False}, None, "-"),
    ("pdc_profile", {"appid": None, "profile_name": None}, None, "Global"),
    ("pdc_profile", {"appid": "1091500", "profile_name": "Cyberpunk 2077"}, None, "Cyberpunk 2077"),
    ("pdc_profile", {"appid": "1091500", "profile_name": None}, None, "Juego 1091500"),
    ("pdc_power", {"watts": 19.7, "gpu_busy": 92}, None, "20W"),
    ("pdc_power", {"watts": 15, "gpu_busy": None}, None, "15W"),
    ("pdc_power", {"watts": None, "gpu_busy": 40}, None, "-"),
    ("pdc_power", {"watts": None, "gpu_busy": None}, None, "-"),
    ("pdc_model", {"model_name": "Legion Go 2", "chip": "Ryzen Z2 Extreme"}, None, "Legion Go 2"),
    ("pdc_model", {"model_name": None}, None, "-"),
    ("pdc_cores", {"cores_active": 6, "cores_max": 8}, None, "6/8"),
    ("pdc_cores", {"cores_active": 6, "cores_max": None}, None, "6"),
    ("pdc_cores", {"cores_active": None}, None, "-"),
    ("pdc_gpu_clock", {"gpu_clock_supported": True, "gpu_clock_manual": True, "gpu_clock_confirmed": True, "gpu_clock_min": 800, "gpu_clock_max": 2700}, None, "800-2700"),
    ("pdc_gpu_clock", {"gpu_clock_supported": True, "gpu_clock_manual": False}, None, "Auto"),
    ("pdc_gpu_clock", {"gpu_clock_supported": False}, None, "-"),
    ("pdc_gpu_clock", {"gpu_clock_supported": True, "gpu_clock_manual": True, "gpu_clock_confirmed": False, "gpu_clock_min": 800, "gpu_clock_max": 2700}, None, "-"),
    ("pdc_charge", {"charge_supported": True, "charge_enabled": True, "charge_confirmed": True, "charge_percent": 80}, None, "80%"),
    ("pdc_charge", {"charge_supported": True, "charge_enabled": False}, None, "Off"),
    ("pdc_charge", {"charge_supported": False}, None, "-"),
    ("pdc_charge", {"charge_supported": True, "charge_enabled": True, "charge_confirmed": False, "charge_percent": 80}, None, "-"),
    ("pdc_bat_health", {"bat_health": 96}, None, "96%"),
    ("pdc_bat_health", {"bat_health": None}, None, "-"),
    ("pdc_fan_rpm", {"fan_rpms": [3200, 3400]}, None, "3200/3400"),
    ("pdc_fan_rpm", {"fan_rpms": [3200]}, None, "3200"),
    ("pdc_fan_rpm", {"fan_rpms": []}, None, "-"),
    ("pdc_eco", {"eco": True}, "es", "Activo"),
    ("pdc_eco", {"eco": False}, "es", "Inactivo"),
    ("pdc_eco", {"eco": False}, "en", "Inactive"),
    ("pdc_auto_tdp", {"auto_tdp": True}, "es", "On"),
    ("pdc_auto_tdp", {"auto_tdp": False}, "es", "Off"),
    ("pdc_smt", {"smt_supported": True, "smt_on": True}, "es", "On"),
    ("pdc_smt", {"smt_supported": True, "smt_on": False}, "es", "Off"),
    ("pdc_smt", {"smt_supported": False}, "es", "-"),
    ("pdc_boost", {"boost_supported": True, "boost_on": True}, "es", "On"),
    ("pdc_boost", {"boost_supported": False}, "es", "-"),
    ("pdc_tdp_learn", {"learn": {"reason": "too_few"}}, "en", "Learning"),
]


@pytest.mark.parametrize(("metric", "snapshot", "locale", "expected"), CASES)
def test_formats_confirmed_states_honestly(metric, snapshot, locale, expected):
    assert pdc.render(metric, snapshot, locale=locale or "es") == expected


@pytest.mark.parametrize("reason", ["no_data", "too_few", "one_level"])
def test_learning_reasons_are_user_facing(reason):
    snapshot = {"learn": {"enough": False, "floor": None, "ceil": None, "reason": reason}}
    assert pdc.render("pdc_tdp_learn", snapshot) == "Aprendiendo"


@pytest.mark.parametrize("metric", ["fps", "pdc_nope"])
def test_unknown_metric_returns_none(metric):
    assert pdc.render(metric, {}) is None


def test_every_formatter_handles_an_empty_snapshot():
    assert all(isinstance(pdc.render(metric, {}), str) for metric in pdc.FORMATTERS)
