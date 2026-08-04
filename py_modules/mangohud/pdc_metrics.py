"""Pure display formatting for the plugin-state HUD metrics ("Panel de Control"
group). Each id turns a snapshot of live plugin state into the short string the
overlay shows as that row's VALUE (the label is emitted separately in config.py).

The values are baked into custom_text, so the strings must stay ASCII — its bundled
font renders box-drawing / fancy glyphs as "?". Never raises and never invents a
number: a missing/None source degrades to a short honest marker."""

DASH = "-"

_TEXT = {
    "es": {
        "auto": "Auto",
        "learning": "Aprendiendo",
        "active": "Activo",
        "inactive": "Inactivo",
        "global": "Global",
        "game": "Juego",
        "on": "On",
        "off": "Off",
        "fan_adaptive": "Adaptativo",
        "fan_silent": "Silencioso",
        "fan_balanced": "Equilibrado",
        "fan_performance": "Rendimiento",
        "fan_custom": "Curva",
    },
    "en": {
        "auto": "Auto",
        "learning": "Learning",
        "active": "Active",
        "inactive": "Inactive",
        "global": "Global",
        "game": "Game",
        "on": "On",
        "off": "Off",
        "fan_adaptive": "Adaptive",
        "fan_silent": "Silent",
        "fan_balanced": "Balanced",
        "fan_performance": "Performance",
        "fan_custom": "Curve",
    },
}
_FAN_MODE = {
    "auto": "auto",
    "adaptive": "fan_adaptive",
    "silent": "fan_silent",
    "balanced": "fan_balanced",
    "performance": "fan_performance",
    "custom": "fan_custom",
}

# tdp_learn reasons that mean "still gathering data" (vs off / no game).
_LEARNING = {"no_data", "too_few", "one_level"}


def _text(snap, key):
    locale = snap.get("_locale")
    return _TEXT[locale if locale in _TEXT else "es"][key]


def _watts(value):
    return f"{round(value)}W" if isinstance(value, (int, float)) else None


def tdp(snap):
    watts = _watts(snap.get("applied")) or DASH
    return f"{_text(snap, 'auto')} {watts}" if snap.get("auto") else watts


def tdp_learn(snap):
    band = snap.get("learn") or {}
    lo, hi = band.get("floor"), band.get("ceil")
    if band.get("enough") and isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
        return f"{round(lo)}-{round(hi)}W"
    return _text(snap, "learning") if band.get("reason") in _LEARNING else DASH


def fan(snap):
    if not snap.get("fan_confirmed"):
        return DASH
    key = _FAN_MODE.get(snap.get("fan_mode"))
    if key is None:
        return DASH
    name = _text(snap, key)
    if snap.get("fan_mode") == "adaptive" and snap.get("fan_learning"):
        return f"{name} ({_text(snap, 'learning').lower()})"
    return name


def eco(snap):
    value = snap.get("eco")
    if value is None:
        return DASH
    return _text(snap, "active" if value else "inactive")


def profile(snap):
    name = snap.get("profile_name")
    if name:
        return str(name)
    appid = snap.get("appid")
    return f"{_text(snap, 'game')} {appid}" if appid else _text(snap, "global")


def power(snap):
    watts = _watts(snap.get("watts"))
    return watts or DASH


def model(snap):
    # Just the model name — the full chip string overruns the row.
    return str(snap.get("model_name") or DASH)


def auto_tdp(snap):
    return _onoff(snap, snap.get("auto_tdp"))


def _onoff(snap, value):
    if value is None:
        return DASH
    return _text(snap, "on" if value else "off")


def charge(snap):
    if not snap.get("charge_supported"):
        return DASH
    if not snap.get("charge_enabled"):
        return _text(snap, "off")
    if not snap.get("charge_confirmed"):
        return DASH
    percent = snap.get("charge_percent")
    return f"{round(percent)}%" if isinstance(percent, (int, float)) else DASH


def bat_health(snap):
    health = snap.get("bat_health")
    return f"{round(health)}%" if isinstance(health, (int, float)) else DASH


def smt(snap):
    return _onoff(snap, snap.get("smt_on")) if snap.get("smt_supported") else DASH


def boost(snap):
    return _onoff(snap, snap.get("boost_on")) if snap.get("boost_supported") else DASH


def cores(snap):
    active = snap.get("cores_active")
    if not isinstance(active, int):
        return DASH
    total = snap.get("cores_max")
    return f"{active}/{total}" if isinstance(total, int) else str(active)


def gpu_clock(snap):
    if not snap.get("gpu_clock_supported"):
        return DASH
    if not snap.get("gpu_clock_manual"):
        return _text(snap, "auto")
    if not snap.get("gpu_clock_confirmed"):
        return DASH
    lo, hi = snap.get("gpu_clock_min"), snap.get("gpu_clock_max")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
        return f"{round(lo)}-{round(hi)}"
    return DASH


def fan_rpm(snap):
    rpms = [r for r in (snap.get("fan_rpms") or []) if isinstance(r, (int, float))]
    return "/".join(str(round(r)) for r in rpms) if rpms else DASH


FORMATTERS = {
    "pdc_tdp": tdp,
    "pdc_tdp_learn": tdp_learn,
    "pdc_auto_tdp": auto_tdp,
    "pdc_fan": fan,
    "pdc_fan_rpm": fan_rpm,
    "pdc_eco": eco,
    "pdc_profile": profile,
    "pdc_power": power,
    "pdc_charge": charge,
    "pdc_bat_health": bat_health,
    "pdc_smt": smt,
    "pdc_boost": boost,
    "pdc_cores": cores,
    "pdc_gpu_clock": gpu_clock,
    "pdc_model": model,
}


def render(metric_id, snapshot, locale="es"):
    """The value string for a pdc metric id, or None if it isn't a pdc metric."""
    fn = FORMATTERS.get(metric_id)
    if fn is None:
        return None
    localized = dict(snapshot)
    localized["_locale"] = locale if locale in _TEXT else "es"
    return fn(localized)
