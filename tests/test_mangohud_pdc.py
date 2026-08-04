from mangohud import pdc_metrics as pdc


# ---- pdc_tdp ----

def test_tdp_auto_with_applied_readback():
    assert pdc.render("pdc_tdp", {"auto": True, "applied": 18}) == "Auto 18W"


def test_tdp_manual_with_applied_readback():
    assert pdc.render("pdc_tdp", {"auto": False, "applied": 20}) == "20W"


def test_tdp_applied_readback_is_not_replaced_by_eco_state():
    assert pdc.render("pdc_tdp", {"auto": True, "applied": 18, "eco": True}) == "Auto 18W"


def test_tdp_without_applied_readback_is_dash():
    assert pdc.render("pdc_tdp", {"auto": False, "applied": None}) == "-"
    assert pdc.render("pdc_tdp", {"auto": True, "applied": None}) == "Auto -"


def test_tdp_rounds_float_applied_readback():
    assert pdc.render("pdc_tdp", {"auto": False, "applied": 19.6}) == "20W"


# ---- pdc_tdp_learn ----

def test_learn_enough_shows_band():
    snap = {"learn": {"enough": True, "floor": 13, "ceil": 19, "reason": "ok"}}
    assert pdc.render("pdc_tdp_learn", snap) == "13-19W"


def test_learn_gathering_says_learning():
    for reason in ("no_data", "too_few", "one_level"):
        snap = {"learn": {"enough": False, "floor": None, "ceil": None, "reason": reason}}
        assert pdc.render("pdc_tdp_learn", snap) == "Aprendiendo"


def test_learn_disabled_or_no_game_is_dash():
    for reason in ("disabled", "no_game", "error"):
        assert pdc.render("pdc_tdp_learn", {"learn": {"reason": reason}}) == "-"


def test_learn_missing_learn_key_is_dash():
    assert pdc.render("pdc_tdp_learn", {}) == "-"


# ---- pdc_fan ----

def test_fan_modes():
    assert pdc.render("pdc_fan", {"fan_mode": "auto", "fan_confirmed": True}) == "Auto"
    assert pdc.render("pdc_fan", {"fan_mode": "custom", "fan_confirmed": True}) == "Curva"
    assert pdc.render("pdc_fan", {"fan_mode": "silent", "fan_confirmed": True}) == "Silencioso"


def test_fan_adaptive_learning_suffix():
    assert pdc.render("pdc_fan", {"fan_mode": "adaptive", "fan_learning": True, "fan_confirmed": True}) == "Adaptativo (aprendiendo)"
    assert pdc.render("pdc_fan", {"fan_mode": "adaptive", "fan_learning": False, "fan_confirmed": True}) == "Adaptativo"


def test_fan_unknown_mode_is_dash():
    assert pdc.render("pdc_fan", {"fan_mode": "???"}) == "-"


def test_fan_intent_without_confirmed_apply_is_dash():
    assert pdc.render("pdc_fan", {
        "fan_mode": "performance",
        "fan_confirmed": False,
    }) == "-"


# ---- pdc_eco ----

def test_eco_on_off():
    assert pdc.render("pdc_eco", {"eco": True}) == "Activo"
    assert pdc.render("pdc_eco", {"eco": False}) == "Inactivo"


# ---- pdc_profile ----

def test_profile_global_when_no_game():
    assert pdc.render("pdc_profile", {"appid": None, "profile_name": None}) == "Global"


def test_profile_prefers_name():
    assert pdc.render("pdc_profile", {"appid": "1091500", "profile_name": "Cyberpunk 2077"}) == "Cyberpunk 2077"


def test_profile_falls_back_to_appid():
    assert pdc.render("pdc_profile", {"appid": "1091500", "profile_name": None}) == "Juego 1091500"


# ---- pdc_power ----

def test_power_only_publishes_measured_watts():
    assert pdc.render("pdc_power", {"watts": 19.7, "gpu_busy": 92}) == "20W"


def test_power_partial_sources():
    assert pdc.render("pdc_power", {"watts": 15, "gpu_busy": None}) == "15W"
    assert pdc.render("pdc_power", {"watts": None, "gpu_busy": 40}) == "-"


def test_power_no_sources_is_dash():
    assert pdc.render("pdc_power", {"watts": None, "gpu_busy": None}) == "-"


# ---- pdc_model (name only — the chip string overruns the row) ----

def test_model_is_name_only():
    assert pdc.render("pdc_model", {"model_name": "Legion Go 2", "chip": "Ryzen Z2 Extreme"}) == "Legion Go 2"


def test_model_missing_is_dash():
    assert pdc.render("pdc_model", {"model_name": None}) == "-"


# ---- pdc_auto_tdp / pdc_smt / pdc_boost (on/off, honest dash when unsupported) ----

def test_auto_tdp_on_off():
    assert pdc.render("pdc_auto_tdp", {"auto_tdp": True}) == "On"
    assert pdc.render("pdc_auto_tdp", {"auto_tdp": False}) == "Off"


def test_smt_boost_gated_on_support():
    assert pdc.render("pdc_smt", {"smt_supported": True, "smt_on": True}) == "On"
    assert pdc.render("pdc_smt", {"smt_supported": True, "smt_on": False}) == "Off"
    assert pdc.render("pdc_smt", {"smt_supported": False}) == "-"
    assert pdc.render("pdc_boost", {"boost_supported": True, "boost_on": True}) == "On"
    assert pdc.render("pdc_boost", {"boost_supported": False}) == "-"


# ---- pdc_cores ----

def test_cores_active_over_max():
    assert pdc.render("pdc_cores", {"cores_active": 6, "cores_max": 8}) == "6/8"
    assert pdc.render("pdc_cores", {"cores_active": 6, "cores_max": None}) == "6"
    assert pdc.render("pdc_cores", {"cores_active": None}) == "-"


# ---- pdc_gpu_clock ----

def test_gpu_clock_manual_range_and_auto():
    assert pdc.render("pdc_gpu_clock", {"gpu_clock_supported": True, "gpu_clock_manual": True, "gpu_clock_confirmed": True, "gpu_clock_min": 800, "gpu_clock_max": 2700}) == "800-2700"
    assert pdc.render("pdc_gpu_clock", {"gpu_clock_supported": True, "gpu_clock_manual": False}) == "Auto"
    assert pdc.render("pdc_gpu_clock", {"gpu_clock_supported": False}) == "-"


def test_gpu_clock_never_formats_an_unconfirmed_requested_range():
    assert pdc.render("pdc_gpu_clock", {
        "gpu_clock_supported": True,
        "gpu_clock_manual": True,
        "gpu_clock_confirmed": False,
        "gpu_clock_min": 800,
        "gpu_clock_max": 2700,
    }) == "-"


# ---- pdc_charge / pdc_bat_health ----

def test_charge_states():
    assert pdc.render("pdc_charge", {"charge_supported": True, "charge_enabled": True, "charge_confirmed": True, "charge_percent": 80}) == "80%"
    assert pdc.render("pdc_charge", {"charge_supported": True, "charge_enabled": False}) == "Off"
    assert pdc.render("pdc_charge", {"charge_supported": False}) == "-"


def test_charge_never_formats_an_unconfirmed_requested_limit():
    assert pdc.render("pdc_charge", {
        "charge_supported": True,
        "charge_enabled": True,
        "charge_confirmed": False,
        "charge_percent": 80,
    }) == "-"


def test_bat_health():
    assert pdc.render("pdc_bat_health", {"bat_health": 96}) == "96%"
    assert pdc.render("pdc_bat_health", {"bat_health": None}) == "-"


# ---- pdc_fan_rpm ----

def test_fan_rpm_joins_present_fans():
    assert pdc.render("pdc_fan_rpm", {"fan_rpms": [3200, 3400]}) == "3200/3400"
    assert pdc.render("pdc_fan_rpm", {"fan_rpms": [3200]}) == "3200"
    assert pdc.render("pdc_fan_rpm", {"fan_rpms": []}) == "-"


# ---- render contract ----

def test_render_unknown_id_returns_none():
    assert pdc.render("fps", {}) is None
    assert pdc.render("pdc_nope", {}) is None


def test_formatters_never_raise_on_empty_snapshot():
    for mid in pdc.FORMATTERS:
        assert isinstance(pdc.render(mid, {}), str)
