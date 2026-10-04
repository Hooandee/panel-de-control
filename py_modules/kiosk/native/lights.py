RGB = tuple[int, int, int]

COLORES_EFFECTS = ("breathing", "rainbow", "wave", "cycle", "spiral", "comet", "sparkle", "ripple", "aurora")
SPECTRUM: tuple[RGB, ...] = ((255, 77, 94), (255, 217, 61), (76, 217, 100), (78, 161, 255), (164, 99, 242), (255, 77, 94))
SWATCHES: tuple[RGB, ...] = (
    (255, 59, 48), (255, 149, 0), (255, 214, 10), (52, 199, 89), (10, 132, 255), (175, 82, 222), (255, 255, 255),
)
OPTIONAL_MODES = (
    ("batteryMode", "battery"), ("temperatureMode", "temperature"), ("performanceMode", "performance"),
    ("clockMode", "clock"), ("audioMode", "vu"), ("ambilight", "ambient"),
)


def rgb(value: dict | None) -> RGB:
    value = value or {}
    return (int(value.get("r", 0)), int(value.get("g", 0)), int(value.get("b", 0)))


def modes(caps: dict | None) -> list[str]:
    if not caps or not caps.get("color"):
        return []
    found = ["solid"]
    if (caps.get("zones") or 0) >= 1:
        found.append("gradient")
    found.append("effect")
    found += [mode for flag, mode in OPTIONAL_MODES if caps.get(flag)]
    return found


def effects(caps: dict | None) -> list[str]:
    supported = (caps or {}).get("supportedEffects") or []
    return [e for e in COLORES_EFFECTS if e in supported] if supported else list(COLORES_EFFECTS)


def target(state: dict) -> tuple[str, str | None]:
    ctx = state.get("profileContext") or {}
    if ctx.get("scope") == "game" and ctx.get("appKey") and not ctx.get("followsGlobal"):
        return "game", ctx["appKey"]
    return "global", None


# Colores stores brightness as a percentage; capabilities.maxBrightness is the LED driver's scale.
BRIGHTNESS_MAX = 100


def swatch(state: dict | None) -> tuple[RGB, ...] | None:
    if not state or not state.get("power"):
        return None
    mode = state.get("mode")
    effect = state.get("effect") or {}
    gradient = tuple(rgb(stop) for stop in state.get("gradient") or [])
    if mode == "solid":
        return (rgb(state.get("color")),)
    if mode == "gradient" and len(gradient) > 1:
        return gradient
    if mode == "effect" and effect.get("useGradient") and len(gradient) > 1:
        return gradient
    if mode == "effect" and effect.get("id") == "breathing":
        return (rgb(state.get("color")),)
    return SPECTRUM
