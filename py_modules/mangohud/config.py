# Metric id -> the MangoHud directive it enables. The item order (below) is the
# on-screen order (MangoHud renders in config order); the pill catalog uses this
# order too, grouped for the UI.
_DIRECTIVE = {
    # FPS
    "fps": "fps",
    "fps_metrics": "fps_metrics",
    "frametime": "frametime",
    "frame_count": "frame_count",
    "show_fps_limit": "show_fps_limit",
    "time": "time",
    # GPU
    "gpu": "gpu_stats",
    "gpu_temp": "gpu_temp",
    "gpu_junction_temp": "gpu_junction_temp",
    "gpu_clock": "gpu_core_clock",
    "gpu_mem_clock": "gpu_mem_clock",
    "gpu_mem_temp": "gpu_mem_temp",
    "gpu_power": "gpu_power",
    "gpu_voltage": "gpu_voltage",
    "gpu_fan": "gpu_fan",
    "gpu_efficiency": "gpu_efficiency",
    "vram": "vram",
    "proc_vram": "proc_vram",
    "gpu_name": "gpu_name",
    # CPU
    "cpu": "cpu_stats",
    "cpu_temp": "cpu_temp",
    "cpu_clock": "cpu_mhz",
    "cpu_power": "cpu_power",
    "cpu_efficiency": "cpu_efficiency",
    "cores": "core_load",
    # Memory
    "ram": "ram",
    "procmem": "procmem",
    "swap": "swap",
    "io_read": "io_read",
    "io_write": "io_write",
    # Battery
    "battery": "battery",
    "battery_watt": "battery_watt",
    "battery_time": "battery_time",
    "device_battery": "device_battery",
    # System
    "resolution": "resolution",
    "refresh_rate": "refresh_rate",
    "arch": "arch",
    "wine": "wine",
    "winesync": "winesync",
    "engine_version": "engine_version",
    "vulkan_driver": "vulkan_driver",
    "present_mode": "present_mode",
    "display_server": "display_server",
    "gamemode": "gamemode",
    "vkbasalt": "vkbasalt",
    "fsr": "fsr",
    "hdr": "hdr",
    "fan": "fan",
    "network": "network",
    "media_player": "media_player",
    "version": "version",
}

# Plugin-state metrics (the "Panel de Control" group). They have no MangoHud
# directive: each shows as a single baked `custom_text=<label> <value>` line. Steam's
# mangoapp does not run `exec` commands, so the value is baked in by main.py at apply
# time (a snapshot; it refreshes on re-apply). The string here is the DEFAULT row label
# (the user can override it — pdc metrics are labellable). Formatting lives in
# pdc_metrics.py.
_PDC_LABEL = {
    "pdc_tdp": "TDP",
    "pdc_tdp_learn": "Banda",
    "pdc_auto_tdp": "Auto",
    "pdc_fan": "Vent.",
    "pdc_fan_rpm": "RPM",
    "pdc_eco": "Descarga",
    "pdc_profile": "Perfil",
    "pdc_power": "Consumo",
    "pdc_charge": "Limite",
    "pdc_bat_health": "Salud",
    "pdc_smt": "SMT",
    "pdc_boost": "Boost",
    "pdc_cores": "Nucleos",
    "pdc_gpu_clock": "GPU MHz",
    "pdc_model": "Equipo",
}
PDC_IDS = frozenset(_PDC_LABEL)

METRIC_CATALOG = tuple(_DIRECTIVE.keys()) + tuple(_PDC_LABEL.keys())


def enabled_pdc_ids(model):
    """The pdc metric ids the (coerced) model currently shows, in item order."""
    return [it["id"] for it in coerce_model(model)["items"]
            if it["kind"] == "metric" and it["id"] in PDC_IDS]


# MangoHud only accepts a per-line custom label for THREE lines. Any other metric
# has no label directive, so a label on it is ignored/stripped.
_LABEL_DIRECTIVE = {"fps": "fps_text", "cpu": "cpu_text", "gpu": "gpu_text"}

# Metrics whose "on" form takes a value instead of =1 (and whose "off" form is
# simply omitted — they aren't part of Steam's default level so nothing leaks).
# `fps_metrics=avg` shows the average; `network=1` = auto-detect the active
# interface (MangoHud reads the first token "1" as "all interfaces bar loopback").
_VALUE_ON = {"device_battery": "gamepad", "fps_metrics": "avg", "network": "1"}

# A drawn divider row (MangoHud has no first-class per-row separator in vertical
# layout, so we emulate one with a custom_text line). MangoHud's font has a
# limited glyph range — box-drawing chars render as "?", so use plain ASCII.
_SEPARATOR_TEXT = "-" * 14

# A spacer emits N empty custom_text lines (an empty custom_text renders a blank
# row = vertical space). Small/medium/large = 1/2/3 blank rows.
_SPACER_LINES = {"small": 1, "medium": 2, "large": 3}

# Colour key -> MangoHud directive it drives (simple key=value ones). MangoHud
# colours by CATEGORY, not per element: gpu/cpu/vram/ram/battery tint that
# category's LABEL word only; `text` (text_color) tints every metric VALUE, all
# custom_text, and the vertical divider together; `frametime` tints the frametime
# graph/number; `background`/`outline` are the box + text-outline colours. FPS is
# special (a 3-stop gradient) and handled separately in `_color_lines`.
_COLOR_DIRECTIVE = {
    "text": "text_color",
    "gpu": "gpu_color",
    "cpu": "cpu_color",
    "vram": "vram_color",
    "ram": "ram_color",
    "battery": "battery_color",
    "frametime": "frametime_color",
    "network": "network_color",
    "background": "background_color",
    "outline": "text_outline_color",
}

_FONT = {"small": 18, "medium": 24, "large": 34}
_POSITIONS = ("top-left", "top-right", "bottom-left", "bottom-right")
_LAYOUTS = ("vertical", "horizontal")
_TEMP_UNITS = ("c", "f")
_ROUND_RADIUS = 8

# A clean, readable-on-dark palette (lighter/pastel so each category stands out
# over a bright game frame). `text` = white values; `fps` = solid white number.
_DEFAULT_COLORS = {
    "text": "ffffff",
    "fps": "ffffff",
    "gpu": "6ee7b7",
    "cpu": "7dd3fc",
    "vram": "c4b5fd",
    "ram": "f0abfc",
    "battery": "fca5a5",
    "frametime": "ffd580",
    "network": "a5b4fc",
    "background": "000000",
    "outline": "000000",
}
_COLOR_KEYS = frozenset(_DEFAULT_COLORS)

_DEFAULT_METRICS = ["fps", "gpu", "cpu", "ram", "battery"]


def _metric_items(ids):
    return [{"kind": "metric", "id": mid} for mid in ids]


DEFAULT_MODEL = {
    "enabled": False,
    # Ordered list of what shows, in screen order. Each item is a metric, a custom
    # text pill, or a separator — so text/dividers can be interleaved and reordered.
    "items": _metric_items(_DEFAULT_METRICS),
    "position": "top-left",
    # Font size in px (global — MangoHud has no per-element size). fontSizeText is the
    # secondary/small text size (labels, custom_text, superscripts).
    "fontSize": 24,
    "fontSizeText": 24,
    "layout": "vertical",
    "compact": False,
    "noSmallFont": False,
    "tempUnit": "c",
    "textOutline": True,
    "textOutlineThickness": 1.0,
    "alpha": 1.0,
    # Vertical padding between rows; the MangoHud default that gives our tight look.
    "cellpaddingY": -0.085,
    "noMargin": False,
    "offsetX": 0,
    "offsetY": 0,
    "fontScale": 1.0,
    "separatorColor": None,
    "colors": dict(_DEFAULT_COLORS),
    "background": {"alpha": 0.5, "roundCorners": True},
}

# Starting points (metric selection only — style stays whatever the user set).
PRESETS = {
    "minimal": ["fps"],
    "balanced": ["fps", "gpu", "cpu", "ram", "battery"],
    "full": [
        "fps", "frametime", "gpu", "gpu_temp", "gpu_power", "vram",
        "cpu", "cpu_temp", "cpu_power", "ram", "battery", "time",
    ],
}


def _is_hex6(value):
    return (
        isinstance(value, str)
        and len(value) == 6
        and all(c in "0123456789abcdef" for c in value.lower())
    )


def _clean_hex(value):
    hexval = value.lstrip("#").lower() if isinstance(value, str) else ""
    return hexval if _is_hex6(hexval) else None


def _coerce_items(raw):
    if not isinstance(raw, list):
        return _metric_items(_DEFAULT_METRICS)
    out = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind == "metric":
            mid = item.get("id")
            if (mid in _DIRECTIVE or mid in PDC_IDS) and mid not in seen:
                seen.add(mid)
                entry = {"kind": "metric", "id": mid}
                # A label is meaningful for the three lines MangoHud can relabel and
                # for the pdc metrics (they render via a custom_text label we emit).
                label = item.get("label")
                if (mid in _LABEL_DIRECTIVE or mid in PDC_IDS) and isinstance(label, str) and label.strip():
                    entry["label"] = label
                out.append(entry)
        elif kind == "text" and isinstance(item.get("text"), str):
            out.append({"kind": "text", "id": str(item.get("id", "")), "text": item["text"]})
        elif kind == "separator":
            out.append({"kind": "separator", "id": str(item.get("id", ""))})
        elif kind == "spacer":
            size = item.get("size")
            out.append({"kind": "spacer", "id": str(item.get("id", "")),
                        "size": size if size in _SPACER_LINES else "small"})
    return out


def _coerce_colors(raw):
    out = dict(_DEFAULT_COLORS)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key not in _COLOR_KEYS:
                continue
            hexval = _clean_hex(value)
            if hexval:
                out[key] = hexval
    return out


def _coerce_float(value, default, lo, hi):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, num))


def _coerce_int(value, default, lo, hi):
    try:
        num = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, num))


def _coerce_background(raw):
    raw = raw if isinstance(raw, dict) else {}
    try:
        alpha = float(raw.get("alpha", DEFAULT_MODEL["background"]["alpha"]))
    except (TypeError, ValueError):
        alpha = DEFAULT_MODEL["background"]["alpha"]
    alpha = max(0.0, min(1.0, alpha))
    return {"alpha": alpha, "roundCorners": bool(raw.get("roundCorners", True))}


def coerce_model(raw):
    """Normalise a possibly-corrupt persisted/incoming model to a known-good shape.
    Never raises — a wrong-typed save must not blow up in render."""
    raw = raw if isinstance(raw, dict) else {}
    position = raw.get("position")
    layout = raw.get("layout")
    temp_unit = raw.get("tempUnit")
    # fontSize (px) replaces the old S/M/L enum; map a legacy `size` for back-compat.
    legacy_size = raw.get("size")
    raw_font = raw.get("fontSize")
    if raw_font is None and isinstance(legacy_size, str) and legacy_size in _FONT:
        font_size = _FONT[legacy_size]
    else:
        font_size = _coerce_int(raw_font, 24, 12, 64)
    return {
        "enabled": bool(raw.get("enabled", False)),
        "items": _coerce_items(raw.get("items")),
        "position": position if position in _POSITIONS else "top-left",
        "fontSize": font_size,
        "fontSizeText": _coerce_int(raw.get("fontSizeText"), 24, 12, 64),
        "layout": layout if layout in _LAYOUTS else "vertical",
        "compact": bool(raw.get("compact", False)),
        "noSmallFont": bool(raw.get("noSmallFont", False)),
        "tempUnit": temp_unit if temp_unit in _TEMP_UNITS else "c",
        "textOutline": bool(raw.get("textOutline", True)),
        "textOutlineThickness": _coerce_float(raw.get("textOutlineThickness", 1.0), 1.0, 0.0, 4.0),
        "alpha": _coerce_float(raw.get("alpha", 1.0), 1.0, 0.0, 1.0),
        "cellpaddingY": _coerce_float(raw.get("cellpaddingY"), -0.085, -0.3, 0.5),
        "noMargin": bool(raw.get("noMargin", False)),
        "offsetX": _coerce_int(raw.get("offsetX"), 0, -2000, 2000),
        "offsetY": _coerce_int(raw.get("offsetY"), 0, -2000, 2000),
        "fontScale": _coerce_float(raw.get("fontScale"), 1.0, 0.5, 2.0),
        "separatorColor": _clean_hex(raw.get("separatorColor")),
        "colors": _coerce_colors(raw.get("colors")),
        "background": _coerce_background(raw.get("background")),
    }


def _style_lines(model):
    # A MangoHud preset MERGES over Steam's default level, so we pin the layout
    # basics: no fps-only collapse, table (not legacy) layout.
    lines = ["fps_only=0", "legacy_layout=0", "hide_engine_names=1"]
    if model["layout"] == "horizontal":
        lines.append("horizontal=1")
    if model["compact"]:
        lines.append("hud_compact=1")
    if model["noMargin"]:
        lines.append("hud_no_margin=1")
    # No table_columns: in the default vertical layout MangoHud renders one element
    # per line (gpu/cpu still group their own sub-metrics on their category row).
    # Emitting table_columns packs metrics across columns, which we don't want.
    lines += [
        f"position={model['position']}",
        f"font_size={model['fontSize']}",
        f"font_size_text={model['fontSizeText']}",
        f"font_scale={model['fontScale']}",
        f"cellpadding_y={model['cellpaddingY']}",
        f"alpha={model['alpha']}",
        f"background_alpha={model['background']['alpha']}",
        f"round_corners={_ROUND_RADIUS if model['background']['roundCorners'] else 0}",
    ]
    # Position nudges — only when set (0 = MangoHud's default, no need to emit).
    if model["offsetX"]:
        lines.append(f"offset_x={model['offsetX']}")
    if model["offsetY"]:
        lines.append(f"offset_y={model['offsetY']}")
    if model["noSmallFont"]:
        lines.append("no_small_font=1")
    if model["tempUnit"] == "f":
        lines.append("temp_fahrenheit=1")
    lines.append(f"text_outline={1 if model['textOutline'] else 0}")
    lines.append(f"text_outline_thickness={model['textOutlineThickness']}")
    if model["separatorColor"]:
        lines.append(f"horizontal_separator_color={model['separatorColor']}")
    lines.extend(_color_lines(model))
    return lines


def _color_lines(model):
    """The colour directives. Most are a plain `directive=hex`. FPS is the one
    exception: MangoHud draws the fps number as a 3-stop gradient and only applies
    `fps_color` when `fps_color_change` is ON — with it OFF the number falls back to
    `text_color` and the fps colour is ignored. So for a SOLID user-chosen fps colour
    we pin all three stops equal and keep the change ON (any fps value maps to the
    same colour)."""
    lines = []
    colors = model["colors"]
    for key, directive in _COLOR_DIRECTIVE.items():
        color = colors.get(key)
        if color:
            lines.append(f"{directive}={color}")
    fps = colors.get("fps")
    if fps:
        lines.append(f"fps_color={fps},{fps},{fps}")
        lines.append("fps_color_change=1")
        # The fps LINE label ("FPS") is drawn with the engine colour, not fps_color,
        # so without this the number takes the chosen colour but the label stays the
        # default red. Tint the engine colour to match so both agree.
        lines.append(f"engine_color={fps}")
    return lines


def _enable_lines(item, values):
    """The directive(s) that turn an enabled metric on, in emit order. A real metric:
    its custom label (only fps/cpu/gpu) then the metric key. A pdc metric: a single
    baked `custom_text=<label> <value>` line — Steam's mangoapp does not run `exec`, so
    the value is baked from the `values` snapshot main.py passes. Without a value (a
    preview of the directives) the label shows alone."""
    mid = item["id"]
    label = item.get("label")
    has_label = isinstance(label, str) and bool(label.strip())
    if mid in PDC_IDS:
        text = label if has_label else _PDC_LABEL[mid]
        value = (values or {}).get(mid)
        return [f"custom_text={text} {value}" if value else f"custom_text={text}"]
    lines = []
    if mid in _LABEL_DIRECTIVE and has_label:
        lines.append(f"{_LABEL_DIRECTIVE[mid]}={label}")
    if mid in _VALUE_ON:
        lines.append(f"{_DIRECTIVE[mid]}={_VALUE_ON[mid]}")
    else:
        lines.append(f"{_DIRECTIVE[mid]}=1")
    return lines


def to_directives(model, values=None):
    """The MangoHud directive lines for the full HUD. Because a preset merges over
    Steam's default level, every real metric is written EXPLICITLY as `=1`/`=0` (so an
    unselected metric can't leak in from the default), and the enabled ones are emitted
    in item order (== on-screen order) with custom text interleaved. pdc metrics have
    no directive; `values` (id -> value string) bakes their live value into the row."""
    model = coerce_model(model)
    enabled = {it["id"] for it in model["items"] if it["kind"] == "metric"}
    lines = _style_lines(model)
    # Turn OFF every real metric not chosen (order irrelevant — they don't show).
    # pdc ids have no directive, so they're never part of this disable set.
    for mid in _DIRECTIVE:
        if mid in enabled or mid in _VALUE_ON:
            # _VALUE_ON metrics aren't in Steam's default level, so an off one is
            # simply omitted (no clean `=0` form for a value directive).
            continue
        lines.append(f"{_DIRECTIVE[mid]}=0")
    # Visible content, in item order.
    for item in model["items"]:
        if item["kind"] == "metric":
            lines.extend(_enable_lines(item, values))
        elif item["kind"] == "separator":
            lines.append(f"custom_text={_SEPARATOR_TEXT}")
        elif item["kind"] == "spacer":
            lines.extend(["custom_text="] * _SPACER_LINES[item["size"]])
        else:
            lines.append(f"custom_text={item['text']}")
    return lines


def directives_for_level(model, level, values=None):
    """The directives for a given Steam overlay level: 0 = off, 1 = minimal (fps
    only, styled), 2..4 = the user's full HUD. `values` bakes the pdc metric values."""
    model = coerce_model(model)
    if level <= 0:
        return ["no_display=1"]
    if level == 1:
        minimal = dict(model)
        minimal["items"] = [{"kind": "metric", "id": "fps"}]
        return to_directives(minimal, values)
    return to_directives(model, values)


def build_presets_conf(model, values=None):
    """The presets.conf text Steam reads for its 5 overlay levels:
    0 = off, 1 = minimal FPS, 2..4 = the user's full HUD. `values` (pdc id -> value
    string) bakes the live plugin-state values into the pdc rows.

    Every preset section is written COMPLETE (level 0 = no_display, level 1 = the full
    minimal HUD, 2..4 = the full HUD — each with an explicit `=0` for every unselected
    metric). MangoHud runs its built-in preset switch + handheld-device override (which
    force metrics like refresh_rate/present_mode/resolution/arch/wine ON) ONLY when it
    can't find the preset in presets.conf; a complete section per level makes it always
    find one, so those defaults never leak into our overlay."""
    model = coerce_model(model)
    out = []
    for level in range(5):
        out.append(f"[preset {level}]")
        out.extend(directives_for_level(model, level, values))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
