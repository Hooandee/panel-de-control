"""OptiScaler.ini schema, image controls and configure overrides shared with the Windows port.

`shared/fixtures/upscalers/settings_parity.json` records what `ini.schema`, `image_settings`, `wiki.resolve_settings` and
the override helpers of `upscalers.service` answer for the cases below. windows/tests/PanelDeControl.Core.Tests/Upscalers
must reach the same answers, in the same order. Rewrite it after a change with
`PYTHONPATH=py_modules python tests/test_upscalers_settings_parity.py --write`.
"""

import json
import sys
import types
from pathlib import Path

for _name in ("pwd", "fcntl"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

from upscalers import catalog, image_settings, ini, service, wiki  # noqa: E402

FIXTURE = Path(__file__).parents[1] / "shared" / "fixtures" / "upscalers" / "settings_parity.json"

SCHEMA_INI = """[Upscalers]
; Select upscaler for DX12 games
; fsr31, xess, fsr21, dlss, fsr22, fsr31_12, xess_12 - Default (auto) is fsr31
Dx12Upscaler=auto

; Select upscaler for Vulkan games
; fsr21, fsr22, dlss - Default (auto) is fsr21
VulkanUpscaler=xess

; ----------------------------------------------------------------

[Log]
; Log to file
; true or false - Default (auto) is true
LogToFile=auto

; Log level
; 0 to 6 - Default (auto) is 2
LogLevel = 2

[Empty]
; nothing but help here

[CAS]
; Enable CAS sharpening
; true or false - Default (auto) is false
Enabled=auto
MotionSharpnessEnabled=auto

[Sharpness]
; Override sharpness
; true or false - Default (auto) is false
OverrideSharpness=false

; Sharpness strength
; Default is 0.3
Sharpness=0.30

[Menu]
; Scale of the overlay
; 0.5 to 2.0 - Default (auto) is 1.0
Scale=1.0
; Overlay position
; a, b (top left), c - Default (auto) is a
Position=zz
; Language, use the code
Lang=en
Enabled=false

[FrameGen]
; Enable frame generation
; true or false - Default (auto) is false
Enabled=false
; Input for frame generation
; nofg, upscaler, nvngxfg - Default (auto) is nofg
FGInput=nofg

[Dangling]
"""
CRLF_INI = SCHEMA_INI.replace("\n", "\r\n")
MANAGED = {"Upscalers.Dx12Upscaler", "Sharpness.Sharpness", "FrameGen.FGInput"}

IMAGE_INI = """[CAS]
Enabled=true
MotionSharpnessEnabled=auto

[Sharpness]
OverrideSharpness=true
Sharpness=0.60

[HelixSR]
Int8=auto
"""
IMAGE_TEXTS = {
    "full": IMAGE_INI,
    "no-motion": IMAGE_INI.replace("MotionSharpnessEnabled=auto\n", ""),
    "motion-true": IMAGE_INI.replace("MotionSharpnessEnabled=auto", "MotionSharpnessEnabled=true"),
    "sharpness-zero": IMAGE_INI.replace("Sharpness=0.60", "Sharpness=0.00"),
    "sharpness-auto": IMAGE_INI.replace("Sharpness=0.60", "Sharpness=auto"),
    "override-false": IMAGE_INI.replace("OverrideSharpness=true", "OverrideSharpness=false"),
    "cas-auto": IMAGE_INI.replace("Enabled=true", "Enabled=auto"),
    "no-helix": IMAGE_INI.replace("[HelixSR]\nInt8=auto\n", ""),
    "only-helix": "[HelixSR]\nInt8=off\n",
    "no-keys": "[Menu]\nScale=1.0\n",
    "crlf": IMAGE_INI.replace("\n", "\r\n"),
    "comments": "; leading\n# hash comment\n" + IMAGE_INI.replace("[CAS]\n", "[CAS]\n# a note\n; another\n"),
    "empty": "",
    "spaced": IMAGE_INI.replace("Enabled=true", "Enabled = true").replace("Sharpness=0.60", "Sharpness   =   0.60  "),
    "bad-int8": IMAGE_INI.replace("Int8=auto", "Int8=maybe"),
    "bad-enabled": IMAGE_INI.replace("Enabled=true", "Enabled=yes"),
    "bad-motion": IMAGE_INI.replace("MotionSharpnessEnabled=auto", "MotionSharpnessEnabled=2"),
    "sharpness-range": IMAGE_INI.replace("Sharpness=0.60", "Sharpness=1.5"),
    "sharpness-negative": IMAGE_INI.replace("Sharpness=0.60", "Sharpness=-0.1"),
    "sharpness-nan": IMAGE_INI.replace("Sharpness=0.60", "Sharpness=nan"),
    "sharpness-inf": IMAGE_INI.replace("Sharpness=0.60", "Sharpness=inf"),
    "sharpness-text": IMAGE_INI.replace("Sharpness=0.60", "Sharpness=high"),
    "sharpness-exponent": IMAGE_INI.replace("Sharpness=0.60", "Sharpness=5e-1"),
    "sharpness-underscore": IMAGE_INI.replace("Sharpness=0.60", "Sharpness=0_5"),
    "dup-key-case": IMAGE_INI.replace("[CAS]\n", "[CAS]\nenabled=false\n"),
    "dup-key-same-case": IMAGE_INI.replace("[CAS]\n", "[CAS]\nEnabled=false\n"),
    "dup-section": IMAGE_INI + "\n[CAS]\nOther=1\n",
    "dup-section-case": IMAGE_INI + "\n[cas]\nOther=1\n",
    "no-equals": IMAGE_INI.replace("[CAS]\n", "[CAS]\njust a line\n"),
    "before-section": "orphan=1\n" + IMAGE_INI,
    "colon": IMAGE_INI.replace("Enabled=true", "Enabled: true"),
    "colon-in-value": IMAGE_INI.replace("[CAS]\n", "[CAS]\nNote=a:b\n"),
    "continuation": IMAGE_INI.replace("Enabled=true\n", "Enabled=true\n   more\n"),
    "continuation-sharpness": IMAGE_INI.replace("Sharpness=0.60\n", "Sharpness=0.6\n  0\n"),
    "indented-section-keys": "[CAS]\n  Enabled=true\n  MotionSharpnessEnabled=auto\n[Sharpness]\n  OverrideSharpness=true\n  Sharpness=0.60\n",
    "hash-after-value": IMAGE_INI.replace("Sharpness=0.60", "Sharpness=0.60 # trailing"),
    "unclosed-section": "[CAS\nEnabled=true\n",
    "empty-key": "[CAS]\n=1\n",
}
CHANGE_REQUESTS = {
    "sharpness-on": {"sharpness": {"enabled": True, "value": 0.5}},
    "sharpness-on-int": {"sharpness": {"enabled": True, "value": 1}},
    "sharpness-on-zero": {"sharpness": {"enabled": True, "value": 0}},
    "sharpness-off": {"sharpness": {"enabled": False, "value": 0.5}},
    "sharpness-0125": {"sharpness": {"enabled": True, "value": 0.125}},
    "sharpness-0375": {"sharpness": {"enabled": True, "value": 0.375}},
    "sharpness-0355": {"sharpness": {"enabled": True, "value": 0.355}},
    "sharpness-0335": {"sharpness": {"enabled": True, "value": 0.335}},
    "int8-on": {"int8": "on"},
    "int8-auto": {"int8": "auto"},
    "int8-max": {"int8": "max"},
    "both": {"sharpness": {"enabled": True, "value": 0.25}, "int8": "off"},
    "empty": {},
    "too-high": {"sharpness": {"enabled": True, "value": 1.5}},
    "negative": {"sharpness": {"enabled": True, "value": -0.01}},
    "missing-value": {"sharpness": {"enabled": True}},
    "missing-enabled": {"sharpness": {"value": 0.5}},
    "enabled-null": {"sharpness": {"enabled": None, "value": 0.5}},
}
CHANGE_TEXTS = ("full", "no-motion", "motion-true", "no-helix", "only-helix", "no-keys", "sharpness-auto", "bad-int8")
FIXED2 = [0.125, 0.375, 0.355, 0.335, 0, 1, 0.5, 0.005, 0.015, 0.025, 0.045, 0.995, 0.994999, 0.1, 0.2, 0.3, 0.6, 0.65,
          0.675, 0.7, 0.85, 1e-9, 0.004999999999999999, 0.285, 0.315]
RESOLVE_REQUESTS = {
    "unique-bool": {"LogToFile": "true"},
    "case-insensitive-key": {"logtofile": "FALSE"},
    "choice-miss": {"LogToFile": "maybe"},
    "ambiguous": {"Enabled": "true"},
    "unknown": {"Nonexistent": "1"},
    "choice-list": {"Dx12Upscaler": "xess_12", "VulkanUpscaler": "xess"},
    "choice-outside": {"VulkanUpscaler": "fsr31"},
    "numeric-free": {"Scale": "1.5", "LogLevel": "3"},
    "numeric-hex": {"Scale": "0x1F"},
    "numeric-negative": {"LogLevel": "-1"},
    "numeric-text": {"Scale": "big"},
    "free-literal": {"Lang": "AUTO", "Scale": "True"},
    "free-sentence": {"Lang": "en us"},
    "several": {"Scale": "2.0", "FGInput": "upscaler", "OverrideSharpness": "true", "Nope": "1", "Enabled": "true"},
    "empty-value": {"Scale": ""},
}

PLANS = {
    "none": None,
    "game-fsrfg": {"input": "fsrfg", "output": "fsrfg", "follows_game": False, "provider": None},
    "game-follows": {"input": "nvngxfg", "output": "auto", "follows_game": True, "provider": None},
    "optiscaler-upscaler": {"input": "upscaler", "output": "fsrfg", "follows_game": False, "provider": None},
    "anr": {"input": "nvngxfg", "output": "auto", "follows_game": True, "provider": "anr"},
}
CHOICES = {
    "default": {},
    "native-off": {"quality": "native", "sharpness": "off", "fg": "off"},
    "quality-soft": {"quality": "quality", "sharpness": "soft", "fg": "off", "model": "full"},
    "balanced-high-fg": {"quality": "balanced", "sharpness": "high", "fg": "on", "fg_route": "game", "model": "lite"},
    "performance-fg-optiscaler": {"quality": "performance", "sharpness": None, "fg": "on", "fg_route": "optiscaler"},
    "ultra-fg-anr": {"quality": "ultra", "sharpness": "soft", "fg": "on", "fg_route": "anr", "model": "unknown"},
    "bogus": {"quality": "extreme", "sharpness": "max", "fg": "maybe", "fg_route": "somewhere", "model": ""},
}
CONFIGURE_CASES = [
    ("beta-balanced-game", "fsr-4.1.2-beta", "balanced-high-fg", "game-fsrfg", False, None),
    ("beta-full-model-fg-off", "fsr-4.1.2-beta", "quality-soft", "game-fsrfg", False, None),
    ("beta-unknown-model-anr", "fsr-4.1.2-beta", "ultra-fg-anr", "anr", True, None),
    ("beta-anr-files-fg-off", "fsr-4.1.2-beta", "native-off", "none", True, None),
    ("beta-image-kept", "fsr-4.1.2-beta", "quality-soft", "game-follows", False,
     {"CAS.Enabled": "true", "Sharpness.OverrideSharpness": "true", "Sharpness.Sharpness": "0.60"}),
    ("beta-image-without-keys", "fsr-4.1.2-beta", "balanced-high-fg", "optiscaler-upscaler", False,
     {"Sharpness.Sharpness": "0.60"}),
    ("fsr31-default", "fsr-3.1", "default", "none", False, None),
    ("fsr31-optiscaler-hudfix", "fsr-3.1", "performance-fg-optiscaler", "optiscaler-upscaler", False, None),
    ("fsr31-bogus", "fsr-3.1", "bogus", "game-fsrfg", False, None),
    ("fsr31-image-kept", "fsr-3.1", "native-off", "none", False,
     {"CAS.Enabled": "false", "Sharpness.OverrideSharpness": "true", "Sharpness.Sharpness": "0.00"}),
    ("xess-fg-on-without-plan", "xess", "balanced-high-fg", "none", False, None),
    ("unknown-build", "does-not-exist", "quality-soft", "game-fsrfg", True, None),
]
MANAGED_INSTALLS = {
    "beta-no-extra": {"build": "fsr-4.1.2-beta"},
    "beta-extra": {"build": "fsr-4.1.2-beta", "managed": ["Plugins.LoadAsiPlugins", "FrameGen.FGNvngxReplacement"]},
    "fsr31-extra": {"build": "fsr-3.1", "managed": ["Zeta.Key", "Alpha.Key"]},
    "unknown-build": {"build": "nope", "managed": ["X.Y"]},
    "no-build": {"managed": ["X.Y"]},
}


def _error(call):
    try:
        return call()
    except image_settings.SettingsError as error:
        return {"error": str(error)}


def _pairs(mapping):
    return [[key, value] for key, value in mapping.items()]


def _image_values():
    return [{"name": name, "text": text, "expected": _error(lambda text=text: image_settings.values(text))}
            for name, text in IMAGE_TEXTS.items()]


def _image_state():
    cases = []
    for name, text in IMAGE_TEXTS.items():
        for helix in (False, True):
            for managed in (False, True):
                cases.append({"name": f"{name}-helix{int(helix)}-managed{int(managed)}", "text": text, "helix": helix,
                              "managed": managed, "expected": _error(lambda: image_settings.state(text, helix, managed))})
    return cases


def _changes(request, text, helix):
    return _error(lambda: _pairs(image_settings.changes(request, image_settings.state(text, helix, False), text)))


def _image_changes():
    cases = []
    for text_name in CHANGE_TEXTS:
        text = IMAGE_TEXTS[text_name]
        for helix in (False, True):
            for name, request in CHANGE_REQUESTS.items():
                cases.append({"name": f"{name}-on-{text_name}-helix{int(helix)}", "request": request, "text": text,
                              "helix": helix, "expected": _changes(request, text, helix)})
    return cases


def _receipt_json(receipt):
    return {"target": receipt["target"], "original": _pairs(receipt["original"]), "applied": _pairs(receipt["applied"])}


def _receipt_run(name, helix, text, steps):
    """The receipt logic of `UpscalerService.set_image_settings` and `restore_image_settings`."""
    initial = text
    target = "game/OptiScaler.ini"
    receipt = None
    results = []
    for step in steps:
        changes = None
        if step["op"] == "set":
            changes = image_settings.changes(step["request"], image_settings.state(text, helix, False), text)
            receipt = json.loads(json.dumps(receipt)) if receipt and receipt.get("target") == target else {
                "target": target, "original": {}, "applied": {}}
            current = image_settings.values(text)
            for key, value in changes.items():
                if key not in receipt["original"] or current.get(key) != receipt["applied"].get(key):
                    receipt["original"][key] = current[key]
                receipt["applied"][key] = value
            text = ini.apply(text, changes)
        elif step["op"] == "restore":
            text = image_settings.restored(text, receipt)
            receipt = None
        elif step["op"] == "edit":
            text = ini.apply(text, step["values"])
        results.append({"text": text, "receipt": _receipt_json(receipt) if receipt else None,
                        **({"changes": _pairs(changes)} if changes is not None else {})})
    return {"name": name, "helix": helix, "text": initial, "target": target, "steps": steps, "results": results}


def _image_receipt():
    on = {"op": "set", "request": {"sharpness": {"enabled": True, "value": 0.25}}}
    off = {"op": "set", "request": {"sharpness": {"enabled": False, "value": 0.25}}}
    int8 = {"op": "set", "request": {"int8": "on"}}
    restore = {"op": "restore"}
    scenarios = {
        "set-restore": [on, restore],
        "set-twice-restore": [on, {"op": "set", "request": {"sharpness": {"enabled": True, "value": 0.75}}}, restore],
        "set-off-restore": [off, restore],
        "user-edit-between": [on, {"op": "edit", "values": {"Sharpness.Sharpness": "0.90"}},
                              {"op": "set", "request": {"sharpness": {"enabled": True, "value": 0.40}}}, restore],
        "user-edit-then-restore": [on, {"op": "edit", "values": {"CAS.Enabled": "false"}}, restore],
        "int8-and-sharpness": [on, int8, restore],
        "int8-twice": [int8, {"op": "set", "request": {"int8": "off"}}, restore],
        "on-then-off": [on, off, restore],
    }
    return [_receipt_run(f"{name}-{text_name}", True, IMAGE_TEXTS[text_name], steps)
            for name, steps in scenarios.items() for text_name in ("full", "no-motion", "motion-true")]


def _fixed2():
    return [{"number": number, "expected": f"{number:.2f}"} for number in FIXED2]


def _resolve_settings():
    return [{"name": name, "settings": _pairs(settings), "expected": _pairs(wiki.resolve_settings(SCHEMA_INI, settings))}
            for name, settings in RESOLVE_REQUESTS.items()]


def _configure():
    cases = []
    for name, build_id, choice_name, plan_name, anr, image in CONFIGURE_CASES:
        choice, plan = CHOICES[choice_name], PLANS[plan_name]
        install = {"build": build_id, "anr": anr, "fg_plan": plan, **({"image_overrides": image} if image else {})}
        build = catalog.BUILDS.get(build_id)
        text = IMAGE_INI.replace("Sharpness=0.60", "Sharpness=0.45") if name.endswith("without-keys") else IMAGE_INI
        model = catalog.model_overrides(build, choice.get("model"))
        fg = catalog.fg_overrides(plan, choice.get("fg") == "on", anr)
        cases.append({
            "name": name, "build": build_id, "choice": choice, "plan": plan, "anr": anr, "image_overrides": image, "text": text,
            "configure": _pairs({**service._option_overrides(choice, reset=True), **model, **fg,
                                 **service._image_overrides(install, text)}),
            "running": _pairs({**service._option_overrides(choice, reset=True), **service._image_overrides(install, text)}),
            "options_only": _pairs(service._option_overrides(choice)),
            "fg_off": _pairs(catalog.fg_overrides(None, False, anr)),
        })
    return cases


def _managed_keys():
    return [{"name": name, "install": install, "expected": sorted(service._managed_keys(install))}
            for name, install in MANAGED_INSTALLS.items()]


def build():
    return {
        "schema": {"text": SCHEMA_INI, "crlf_text": CRLF_INI, "managed": sorted(MANAGED),
                   "expected": ini.schema(SCHEMA_INI, MANAGED), "crlf_expected": ini.schema(CRLF_INI, MANAGED),
                   "no_managed_expected": ini.schema(SCHEMA_INI), "empty_expected": ini.schema(""),
                   "no_sections_expected": ini.schema("Key=1\n; help\n")},
        "image_values": _image_values(),
        "image_state": _image_state(),
        "image_changes": _image_changes(),
        "image_receipt": _image_receipt(),
        "fixed2": _fixed2(),
        "resolve_settings": _resolve_settings(),
        "configure": _configure(),
        "managed_keys": _managed_keys(),
    }


def test_settings_match_the_shared_fixture():
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == json.loads(json.dumps(build()))


def test_fixture_covers_the_edge_cases():
    fixture = build()
    errors = {case["expected"]["error"] for case in fixture["image_values"] if "error" in case["expected"]}
    assert errors == {"invalid_config"}
    assert sum("error" in case["expected"] for case in fixture["image_changes"]) > 20
    assert any(key["choices"] and key["value"] == key["choices"][-1] and key["value"] not in ("auto", "true", "false")
               for section in fixture["schema"]["expected"] for key in section["keys"])
    assert all(section["keys"] for section in fixture["schema"]["expected"])


if __name__ == "__main__" and "--write" in sys.argv:
    with FIXTURE.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(build(), separators=(",", ":"), ensure_ascii=False) + "\n")
