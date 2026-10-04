FPS_TARGETS = (30, 40, 45, 60, 90, 120, 144)
MAX_FPS_ORBS = 5
MIN_TARGET_FPS = 20
COMMON_RATES = (60, 90, 120)
FAN_CHOICES = ("auto", "silent", "balanced", "performance")


def fps_choices(max_fps: float | None) -> list[int]:
    ceiling = max(MIN_TARGET_FPS, max_fps if max_fps is not None else 60)
    reachable = [fps for fps in FPS_TARGETS if fps <= ceiling]
    if len(reachable) <= MAX_FPS_ORBS:
        return reachable
    return [fps for fps in reachable if fps != 45][-MAX_FPS_ORBS:]


def refresh_choices(refresh: dict | None) -> list[int]:
    if not refresh or refresh.get("settable") is False:
        return []
    low, high = refresh.get("min"), refresh.get("max")
    if low is None or high is None:
        return []
    rates = [low, *(hz for hz in COMMON_RATES if low < hz < high), high]
    return list(dict.fromkeys(rates))


def fan_choices(fan: dict | None) -> list[str]:
    if not fan or not fan.get("supported"):
        return []
    offered = {"auto", *(preset.get("id") for preset in fan.get("presets") or [])}
    choices = [preset for preset in FAN_CHOICES if preset in offered]
    return choices if len(choices) > 1 else []


def level_caption(frequencies: dict | None, level: int | None, decimal_comma: bool) -> str:
    entry = (frequencies or {}).get(str(level)) if level is not None else None
    if not entry or not entry.get("cpu_khz"):
        return ""
    ghz = f"{max(entry['cpu_khz']) / 1e6:.1f}"
    if decimal_comma:
        ghz = ghz.replace(".", ",")
    return f"{ghz} GHz · {entry['gpu_mhz']} MHz"


def step_at(offset: float, size: float, pad: float, low: int, high: int) -> int:
    span = size - 2 * pad
    fraction = min(1.0, max(0.0, (offset - pad) / span)) if span > 0 else 0.0
    return round(low + fraction * (high - low))
