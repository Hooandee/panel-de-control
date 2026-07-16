"""Pure display formatting for the plugin-state HUD metrics ("Panel de Control"
group). Each id turns a snapshot of live plugin state into the short string the
overlay shows as that row's VALUE (the label is emitted separately in config.py).

The values are baked into custom_text, so the strings must stay ASCII — its bundled
font renders box-drawing / fancy glyphs as "?". Never raises and never invents a
number: a missing/None source degrades to a short honest marker."""

DASH = "-"

_FAN_MODE = {
    "auto": "Auto",
    "adaptive": "Adaptativo",
    "silent": "Silencioso",
    "balanced": "Equilibrado",
    "performance": "Rendimiento",
    "custom": "Curva",
}

# tdp_learn reasons that mean "still gathering data" (vs off / no game).
_LEARNING = {"no_data", "too_few", "one_level"}


def _watts(value):
    return f"{round(value)}W" if isinstance(value, (int, float)) else None


def tdp(snap):
    if snap.get("eco"):
        return "Descarga"
    watts = _watts(snap.get("setpoint")) or DASH
    return f"Auto {watts}" if snap.get("auto") else watts


def tdp_learn(snap):
    band = snap.get("learn") or {}
    lo, hi = band.get("floor"), band.get("ceil")
    if band.get("enough") and isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
        return f"{round(lo)}-{round(hi)}W"
    return "Aprendiendo" if band.get("reason") in _LEARNING else DASH


def fan(snap):
    name = _FAN_MODE.get(snap.get("fan_mode"))
    if name is None:
        return DASH
    if snap.get("fan_mode") == "adaptive" and snap.get("fan_learning"):
        return f"{name} (aprendiendo)"
    return name


def eco(snap):
    return "Activo" if snap.get("eco") else "Inactivo"


def profile(snap):
    name = snap.get("profile_name")
    if name:
        return str(name)
    appid = snap.get("appid")
    return f"Juego {appid}" if appid else "Global"


def power(snap):
    parts = []
    watts = _watts(snap.get("watts"))
    if watts:
        parts.append(watts)
    gpu = snap.get("gpu_busy")
    if isinstance(gpu, (int, float)):
        parts.append(f"{round(gpu)}%")
    return " ".join(parts) if parts else DASH


def model(snap):
    # Just the model name — the full chip string overruns the row.
    return str(snap.get("model_name") or DASH)


def auto_tdp(snap):
    return _onoff(snap.get("auto_tdp"))


def _onoff(value):
    if value is None:
        return DASH
    return "On" if value else "Off"


def charge(snap):
    if not snap.get("charge_supported"):
        return DASH
    if not snap.get("charge_enabled"):
        return "Off"
    percent = snap.get("charge_percent")
    return f"{round(percent)}%" if isinstance(percent, (int, float)) else DASH


def bat_health(snap):
    health = snap.get("bat_health")
    return f"{round(health)}%" if isinstance(health, (int, float)) else DASH


def smt(snap):
    return _onoff(snap.get("smt_on")) if snap.get("smt_supported") else DASH


def boost(snap):
    return _onoff(snap.get("boost_on")) if snap.get("boost_supported") else DASH


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
        return "Auto"
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


def render(metric_id, snapshot):
    """The value string for a pdc metric id, or None if it isn't a pdc metric."""
    fn = FORMATTERS.get(metric_id)
    return fn(snapshot) if fn else None
