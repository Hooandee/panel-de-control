import pytest

from mangohud.config import (
    DEFAULT_MODEL,
    METRIC_CATALOG,
    PRESETS,
    build_presets_conf,
    coerce_model,
    directives_for_level,
    to_directives,
)


def _metrics(*ids):
    return [{"kind": "metric", "id": i} for i in ids]


def _section(text, name):
    """Return the lines of [preset <name>] up to the next section/EOF."""
    lines = text.splitlines()
    start = lines.index(f"[preset {name}]") + 1
    out = []
    for line in lines[start:]:
        if line.startswith("[preset "):
            break
        if line.strip():
            out.append(line.strip())
    return out


# ---- coerce_model: shape validation (a bad persisted model must never throw) ----

def test_coerce_garbage_returns_defaults():
    assert coerce_model(None) == DEFAULT_MODEL
    assert coerce_model("nope") == DEFAULT_MODEL
    assert coerce_model(42) == DEFAULT_MODEL


def test_coerce_fills_missing_keys():
    m = coerce_model({"items": _metrics("fps")})
    assert m["position"] == DEFAULT_MODEL["position"]
    assert m["fontSize"] == DEFAULT_MODEL["fontSize"]
    assert m["layout"] == "vertical"
    assert "alpha" in m["background"]
    assert m["locale"] == "es"


def test_hud_locale_round_trips_and_rejects_unknown_values():
    assert coerce_model({"locale": "en"})["locale"] == "en"
    assert coerce_model({"locale": "fr"})["locale"] == "es"


def test_coerce_drops_unknown_metrics_and_dedupes_keeping_order():
    m = coerce_model({"items": _metrics("fps", "bogus", "cpu", "fps")})
    assert m["items"] == _metrics("fps", "cpu")


def test_coerce_inserts_required_block_parents():
    m = coerce_model({"items": _metrics("battery_watt", "cpu_temp")})
    assert m["items"] == _metrics("battery", "battery_watt", "cpu", "cpu_temp")


def test_coerce_keeps_text_items_interleaved_in_order():
    m = coerce_model({"items": [
        {"kind": "metric", "id": "fps"},
        {"kind": "text", "id": "a", "text": "hola"},
        {"kind": "metric", "id": "gpu"},
        {"kind": "text"},  # no text -> dropped
    ]})
    assert m["items"] == [
        {"kind": "metric", "id": "fps"},
        {"kind": "text", "id": "a", "text": "hola"},
        {"kind": "metric", "id": "gpu"},
    ]


def test_coerce_bad_position_size_layout_fall_back():
    m = coerce_model({"position": "middle", "fontSize": "huge", "layout": "diagonal"})
    assert m["position"] == "top-left"
    assert m["fontSize"] == 24  # garbage font size -> default
    assert m["layout"] == "vertical"


def test_coerce_non_finite_numbers_fall_back_without_raising():
    m = coerce_model({
        "fontSize": float("inf"),
        "offsetX": float("-inf"),
        "fontScale": float("nan"),
        "background": {"alpha": float("nan")},
    })
    assert m["fontSize"] == DEFAULT_MODEL["fontSize"]
    assert m["offsetX"] == DEFAULT_MODEL["offsetX"]
    assert m["fontScale"] == DEFAULT_MODEL["fontScale"]
    assert m["background"]["alpha"] == DEFAULT_MODEL["background"]["alpha"]


def test_coerce_clamps_background_alpha():
    assert coerce_model({"background": {"alpha": 5}})["background"]["alpha"] == 1.0
    assert coerce_model({"background": {"alpha": -2}})["background"]["alpha"] == 0.0


def test_coerce_rejects_non_boolean_toggle_values():
    model = coerce_model({
        "enabled": "false",
        "compact": 1,
        "noSmallFont": [],
        "textOutline": None,
        "noMargin": "true",
        "background": {"roundCorners": 0},
    })

    assert model["enabled"] is DEFAULT_MODEL["enabled"]
    assert model["compact"] is DEFAULT_MODEL["compact"]
    assert model["noSmallFont"] is DEFAULT_MODEL["noSmallFont"]
    assert model["textOutline"] is DEFAULT_MODEL["textOutline"]
    assert model["noMargin"] is DEFAULT_MODEL["noMargin"]
    assert model["background"]["roundCorners"] is DEFAULT_MODEL["background"]["roundCorners"]


def test_coerce_assigns_bounded_unique_ids_and_limits_custom_rows():
    items = [
        {"kind": "text", "id": "", "text": "one"},
        {"kind": "text", "id": "duplicate", "text": "two"},
        {"kind": "text", "id": "duplicate", "text": "three"},
        {"kind": "separator", "id": "x" * 100},
        *({"kind": "spacer", "id": "", "size": "small"} for _ in range(200)),
    ]

    coerced = coerce_model({"items": items})["items"]
    ids = [(item["kind"], item["id"]) for item in coerced]

    assert len(coerced) <= 128
    assert len(ids) == len(set(ids))
    assert all(1 <= len(item_id) <= 64 for _, item_id in ids)


def test_coerce_strips_hash_and_validates_hex_colors():
    m = coerce_model({"colors": {"gpu": "#AABBCC", "cpu": "xyz", "bogus": "ffffff"}})
    assert m["colors"]["gpu"] == "aabbcc"  # hash stripped, lowercased
    assert m["colors"]["cpu"] == DEFAULT_MODEL["colors"]["cpu"]  # invalid hex -> default
    assert "bogus" not in m["colors"]  # unknown category dropped
    assert set(m["colors"]) == set(DEFAULT_MODEL["colors"])  # always the full palette


# ---- to_directives: model -> MangoHud directive lines ----

def test_selected_metrics_are_enabled_explicitly():
    lines = to_directives(coerce_model({"items": _metrics("fps", "gpu", "cpu_temp")}))
    assert "fps=1" in lines
    assert "gpu_stats=1" in lines
    assert "cpu_temp=1" in lines


def test_unselected_catalog_metrics_are_disabled_explicitly():
    # a preset merges over Steam's default, so unchosen metrics must be turned off
    lines = to_directives(coerce_model({"items": _metrics("fps")}))
    assert "gpu_stats=0" in lines
    assert "vram=0" in lines
    assert "battery=0" in lines
    assert "fps=1" in lines


def test_item_order_is_preserved_for_enabled_metrics():
    lines = to_directives(coerce_model({"items": _metrics("cpu", "fps")}))
    assert lines.index("cpu_stats=1") < lines.index("fps=1")


@pytest.mark.parametrize(
    ("field", "on", "off", "directive"),
    [
        ("layout", "horizontal", "vertical", "horizontal=1"),
        ("compact", True, False, "hud_compact=1"),
        ("noMargin", True, False, "hud_no_margin=1"),
        ("noSmallFont", True, False, "no_small_font=1"),
        ("tempUnit", "f", "c", "temp_fahrenheit=1"),
    ],
)
def test_optional_directives_are_emitted_only_when_enabled(field, on, off, directive):
    assert directive in to_directives(coerce_model({field: on}))
    assert directive not in to_directives(coerce_model({field: off}))


def test_style_directives_present():
    lines = to_directives(coerce_model({"position": "bottom-right", "fontSize": 34}))
    assert "position=bottom-right" in lines
    assert "font_size=34" in lines


def test_colors_emitted_without_hash():
    lines = to_directives(coerce_model({"colors": {"gpu": "#112233"}}))
    assert "gpu_color=112233" in lines
    assert not any("#" in line for line in lines)


def test_custom_text_pills_emitted():
    lines = to_directives(coerce_model({"items": [{"kind": "text", "id": "1", "text": "PdC"}]}))
    assert "custom_text=PdC" in lines


def test_custom_text_and_labels_cannot_inject_directives():
    lines = to_directives(coerce_model({"items": [
        {"kind": "metric", "id": "fps", "label": "Frames\nno_display=1"},
        {"kind": "text", "id": "1", "text": "hello\r\nposition=middle"},
    ]}))
    assert "fps_text=Frames no_display=1" in lines
    assert "custom_text=hello position=middle" in lines
    assert "no_display=1" not in lines
    assert "position=middle" not in lines


def test_baked_values_cannot_inject_directives():
    lines = to_directives(
        coerce_model({"items": [{"kind": "metric", "id": "pdc_profile"}]}),
        {"pdc_profile": "Game\nno_display=1"},
    )
    assert "custom_text=Perfil Game no_display=1" in lines
    assert "no_display=1" not in lines


def test_background_alpha_and_round_corners():
    lines = to_directives(coerce_model({"background": {"alpha": 0.5, "roundCorners": True}}))
    assert "background_alpha=0.5" in lines
    assert any(line.startswith("round_corners=") for line in lines)
    off = to_directives(coerce_model({"background": {"alpha": 0.5, "roundCorners": False}}))
    assert "round_corners=0" in off


# ---- build_presets_conf: the file Steam reads ----

def test_presets_conf_has_all_five_levels():
    text = build_presets_conf(coerce_model({"items": _metrics("fps", "gpu")}))
    for n in range(5):
        assert f"[preset {n}]" in text


def test_preset_0_is_off_and_1_is_minimal_fps():
    model = coerce_model({"items": _metrics("fps", "gpu", "cpu")})
    text = build_presets_conf(model)
    assert _section(text, "0") == ["no_display=1"]
    # Every level section is COMPLETE (matches directives_for_level) so MangoHud never
    # falls back to its built-in preset/handheld override → no default metrics leak.
    assert _section(text, "1") == directives_for_level(model, 1)


def test_minimal_preset_omits_unselected_unguarded_metrics():
    # In MangoHud's ordered layout these render when their directive is present,
    # even with value 0. A custom preset does not inherit Steam's built-in level.
    lines = directives_for_level(coerce_model({"items": _metrics("fps")}), 1)
    assert "fps=1" in lines
    assert not any(line.startswith("present_mode=") for line in lines)
    assert not any(line.startswith("refresh_rate=") for line in lines)
    assert not any(line.startswith("hdr=") for line in lines)
    assert not any(line.startswith("winesync=") for line in lines)
    for leak in ("resolution=0", "arch=0", "wine=0"):
        assert leak in lines


def test_presets_2_to_4_carry_the_full_hud():
    model = coerce_model({"items": _metrics("fps", "gpu")})
    text = build_presets_conf(model)
    full = to_directives(model)
    for n in ("2", "3", "4"):
        assert _section(text, n) == full


# ---- catalog + presets ----

def test_presets_reference_only_catalog_ids():
    for name, ids in PRESETS.items():
        assert set(ids) <= set(METRIC_CATALOG), name


def test_expanded_catalog_has_the_new_metrics():
    for mid in ("gpu_name", "swap", "io_read", "io_write", "battery_watt",
                "battery_time", "device_battery", "resolution", "arch", "wine",
                "engine_version", "fan"):
        assert mid in METRIC_CATALOG


def test_full_metric_catalog_present():
    # The full MangoHud displayable surface — every id serialises to its directive.
    expected = {
        "gpu_junction_temp": "gpu_junction_temp", "gpu_mem_temp": "gpu_mem_temp",
        "gpu_mem_clock": "gpu_mem_clock", "gpu_voltage": "gpu_voltage",
        "gpu_fan": "gpu_fan", "gpu_efficiency": "gpu_efficiency",
        "proc_vram": "proc_vram", "cpu_efficiency": "cpu_efficiency",
        "procmem": "procmem", "frame_count": "frame_count",
        "show_fps_limit": "show_fps_limit", "vulkan_driver": "vulkan_driver",
        "present_mode": "present_mode", "gamemode": "gamemode",
        "vkbasalt": "vkbasalt", "fsr": "fsr", "hdr": "hdr",
        "refresh_rate": "refresh_rate", "display_server": "display_server",
        "winesync": "winesync", "version": "version", "media_player": "media_player",
    }
    for mid, directive in expected.items():
        assert mid in METRIC_CATALOG, mid
        assert f"{directive}=1" in to_directives(coerce_model({"items": _metrics(mid)})), mid


def test_value_form_metrics_emit_value_and_omit_when_off():
    for mid, on in (("fps_metrics", "fps_metrics=avg"), ("network", "network=1")):
        assert on in to_directives(coerce_model({"items": _metrics(mid)}))
        off = to_directives(coerce_model({"items": _metrics("fps")}))
        # "omitted when off" = no directive whose exact key is `mid` (must not
        # collide with e.g. `network_color`, which is always emitted).
        assert not any(ln.split("=", 1)[0] == mid for ln in off), mid


def test_network_color_emitted_when_set():
    lines = to_directives(coerce_model({"colors": {"network": "#abcdef"}}))
    assert "network_color=abcdef" in lines


# ---- font size: fine px control + secondary text size + legacy back-compat ----

@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("fontSize", 40, 40),
        ("fontSize", 4, 12),
        ("fontSize", 999, 64),
        ("fontSize", "x", 24),
        ("fontSizeText", 4, 12),
        ("fontSizeText", 999, 64),
        ("fontSizeSecondary", 18, 18),
        ("fontSizeSecondary", 4, 6),
        ("fontSizeSecondary", 999, 24),
        ("cellpaddingY", 0.3, 0.3),
        ("cellpaddingY", -5, -0.3),
        ("cellpaddingY", 5, 0.5),
        ("cellpaddingY", "x", -0.085),
        ("alpha", 0.4, 0.4),
        ("alpha", 5, 1.0),
        ("alpha", -2, 0.0),
        ("alpha", "nope", 1.0),
        ("fontScale", 1.5, 1.5),
        ("fontScale", 0.1, 0.5),
        ("fontScale", 9, 2.0),
        ("textOutlineThickness", -3, 0.0),
    ],
)
def test_numeric_style_fields_are_validated(field, value, expected):
    assert coerce_model({field: value})[field] == expected


@pytest.mark.parametrize(
    ("model", "directive"),
    [
        ({}, "cellpadding_y=-0.085"),
        ({}, "alpha=1.0"),
        ({}, "font_scale=1.0"),
        ({"fontSize": 40}, "font_size=40"),
        ({"fontSizeSecondary": 18}, "font_size_secondary=18"),
        ({"cellpaddingY": 0.2}, "cellpadding_y=0.2"),
        ({"alpha": 0.4}, "alpha=0.4"),
        ({"fontScale": 1.5}, "font_scale=1.5"),
        ({"textOutlineThickness": 1.5}, "text_outline_thickness=1.5"),
    ],
)
def test_numeric_style_fields_emit_their_directive(model, directive):
    assert directive in to_directives(coerce_model(model))


def test_numeric_style_defaults():
    model = coerce_model({})
    assert model["fontSize"] == 24
    assert model["fontSizeSecondary"] == 13
    assert model["cellpaddingY"] == -0.085
    assert model["alpha"] == 1.0
    assert model["fontScale"] == 1.0


def test_font_size_back_compat_from_old_enum():
    assert coerce_model({"size": "small"})["fontSize"] == 18
    assert coerce_model({"size": "medium"})["fontSize"] == 24
    assert coerce_model({"size": "large"})["fontSize"] == 34
    # an explicit fontSize wins over a stale legacy size
    assert coerce_model({"size": "small", "fontSize": 50})["fontSize"] == 50


def test_font_size_text_remains_an_independent_media_font():
    model = coerce_model({
        "fontSize": 40,
        "fontSizeText": 16,
        "separateTextSize": False,
    })
    assert "separateTextSize" not in model
    assert model["fontSizeText"] == 16
    assert "font_size_text=16" in to_directives(model)


def test_secondary_font_never_exceeds_main_font():
    assert coerce_model({"fontSize": 16, "fontSizeSecondary": 30})["fontSizeSecondary"] == 16


# ---- Avanzado: cellpadding_y / offsets / text alpha / font_scale / no_margin ----

def test_offsets_default_zero_and_emit_only_when_set():
    m = coerce_model({})
    assert m["offsetX"] == 0 and m["offsetY"] == 0
    off = to_directives(m)
    assert not any(ln.startswith("offset_x=") or ln.startswith("offset_y=") for ln in off)
    on = to_directives(coerce_model({"offsetX": 12, "offsetY": -8}))
    assert "offset_x=12" in on
    assert "offset_y=-8" in on
    # out-of-range clamps; garbage -> default 0
    assert coerce_model({"offsetX": 9000})["offsetX"] == 2000
    assert coerce_model({"offsetY": "x"})["offsetY"] == 0


def test_table_columns_never_emitted():
    # A vertical HUD is one element per line — no column packing.
    assert not any(ln.startswith("table_columns") for ln in to_directives(coerce_model({})))


# ---- per-metric custom labels (only fps/cpu/gpu) ----

def test_label_emits_text_directive_for_fps_cpu_gpu():
    lines = to_directives(coerce_model({"items": [
        {"kind": "metric", "id": "fps", "label": "Cuadros"},
        {"kind": "metric", "id": "cpu", "label": "Proc"},
        {"kind": "metric", "id": "gpu", "label": "Gráfica"},
    ]}))
    assert "fps_text=Cuadros" in lines
    assert "cpu_text=Proc" in lines
    assert "gpu_text=Gráfica" in lines


def test_label_stripped_on_unsupported_metric():
    m = coerce_model({"items": [{"kind": "metric", "id": "vram", "label": "nope"}]})
    assert m["items"] == _metrics("gpu", "vram")
    labels = ("fps_text=", "cpu_text=", "gpu_text=")
    assert not any(ln.startswith(labels) for ln in to_directives(m))


def test_empty_label_is_dropped():
    m = coerce_model({"items": [{"kind": "metric", "id": "fps", "label": "  "}]})
    assert m["items"] == [{"kind": "metric", "id": "fps"}]
    assert not any(ln.startswith("fps_text=") for ln in to_directives(m))


# ---- separators ----

def test_separator_item_kept_and_emits_a_divider_line():
    m = coerce_model({"items": [
        {"kind": "metric", "id": "fps"},
        {"kind": "separator", "id": "s1"},
        {"kind": "metric", "id": "gpu"},
    ]})
    assert m["items"][1] == {"kind": "separator", "id": "s1"}
    lines = to_directives(m)
    # ASCII divider (MangoHud font has no box-drawing glyphs -> "?"), never "─"
    divider = [ln for ln in lines if ln.startswith("custom_text=") and set(ln.split("=", 1)[1]) == {"-"}]
    assert len(divider) == 1
    assert "─" not in "".join(lines)
    # the divider sits between the two metrics, in order
    assert lines.index("fps=1") < lines.index(divider[0]) < lines.index("gpu_stats=1")


# ---- global style additions ----

def test_invalid_temperature_unit_falls_back_to_celsius():
    assert coerce_model({"tempUnit": "kelvin"})["tempUnit"] == "c"


# ---- device_battery: value directive, omitted when off ----

def test_device_battery_on_uses_value_and_off_is_omitted():
    on = to_directives(coerce_model({"items": _metrics("device_battery")}))
    assert "device_battery=gamepad" in on
    off = to_directives(coerce_model({"items": _metrics("fps")}))
    assert not any(ln.startswith("device_battery") for ln in off)


def test_new_metrics_disabled_explicitly_when_unselected():
    lines = to_directives(coerce_model({"items": _metrics("fps")}))
    for directive in ("gpu_name=0", "swap=0", "io_read=0", "engine_version=0", "fan=0"):
        assert directive in lines


# ---- colours: MangoHud ground truth ----

def test_text_color_drives_values_and_custom_text():
    lines = to_directives(coerce_model({"colors": {"text": "#abcdef"}}))
    assert "text_color=abcdef" in lines


def test_fps_is_a_solid_colour_not_a_gradient():
    # MangoHud only honours fps_color when fps_color_change is ON; with it off the
    # fps number falls back to text_color. A solid pick = all stops equal + change ON.
    lines = to_directives(coerce_model({"colors": {"fps": "#12ab34"}}))
    assert "fps_color=12ab34,12ab34,12ab34" in lines
    assert "fps_color_change=1" in lines
    assert "fps_color_change=0" not in lines


def test_frametime_background_and_outline_colours_emitted():
    lines = to_directives(coerce_model({"colors": {
        "frametime": "#111111", "background": "#222222", "outline": "#333333",
    }}))
    assert "frametime_color=111111" in lines
    assert "background_color=222222" in lines
    assert "text_outline_color=333333" in lines


def test_text_outline_toggle():
    assert "text_outline=1" in to_directives(coerce_model({"textOutline": True}))
    assert "text_outline=0" in to_directives(coerce_model({"textOutline": False}))
    assert coerce_model({})["textOutline"] is True  # MangoHud default


# ---- level directives ----

def test_directives_for_level_off_minimal_full():
    model = coerce_model({"items": _metrics("fps", "gpu", "cpu")})
    assert directives_for_level(model, 0) == ["no_display=1"]
    minimal = directives_for_level(model, 1)
    assert "fps=1" in minimal and "gpu_stats=1" not in minimal  # fps only
    for level in (2, 3, 4):
        assert directives_for_level(model, level) == to_directives(model)


# ---- pdc metrics: a single baked custom_text=<label> <value> line ----

@pytest.mark.parametrize(
    ("model", "values", "expected"),
    [
        ({"items": _metrics("fps", "pdc_tdp")}, {"pdc_tdp": "21W"}, "custom_text=TDP 21W"),
        ({"items": [{"kind": "metric", "id": "pdc_tdp", "label": "Potencia"}]}, {"pdc_tdp": "18W"}, "custom_text=Potencia 18W"),
        ({"items": _metrics("pdc_fan")}, {}, "custom_text=Vent."),
        ({"items": _metrics("pdc_charge")}, {"pdc_charge": "-"}, "custom_text=Limite -"),
        ({"locale": "es", "items": _metrics("pdc_power")}, {}, "custom_text=Consumo"),
        ({"locale": "en", "items": _metrics("pdc_power")}, {}, "custom_text=Power"),
    ],
)
def test_pdc_metrics_emit_one_baked_custom_text_line(model, values, expected):
    # Live reloads do not execute MangoHud preset commands, so dynamic values
    # must remain a single baked row instead of an exec-backed second row.
    lines = to_directives({**model, "enabled": True}, values)
    assert [line for line in lines if line.startswith("custom_text=")] == [expected]
    assert not any(line.startswith("exec=") for line in lines)


def test_pdc_metric_has_no_zero_disable_directive():
    # pdc ids have no MangoHud directive, so the =0 disable loop must never touch them.
    lines = to_directives({"items": _metrics("fps"), "enabled": True}, {})
    assert not any(line.startswith("pdc_") for line in lines)


def test_pdc_metric_coerced_and_labellable():
    m = coerce_model({"items": [{"kind": "metric", "id": "pdc_power", "label": "W"}]})
    assert m["items"] == [{"kind": "metric", "id": "pdc_power", "label": "W"}]


def test_enabled_pdc_ids():
    from mangohud.config import enabled_pdc_ids
    model = {"items": _metrics("fps", "pdc_tdp", "gpu", "pdc_power")}
    assert enabled_pdc_ids(model) == ["pdc_tdp", "pdc_power"]


def test_presets_conf_bakes_pdc_value():
    conf = build_presets_conf({"items": _metrics("pdc_tdp"), "enabled": True}, {"pdc_tdp": "21W"})
    assert "custom_text=TDP 21W" in conf
