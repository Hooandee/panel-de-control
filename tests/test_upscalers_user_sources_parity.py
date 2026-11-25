"""User mods and user-supplied recipe files shared with the Windows port.

`shared/fixtures/upscalers/user_sources_parity.json` records what `upscalers.user_mods` (`layout`, `replaces_optiscaler`)
and `upscalers.user_deps` (`_filename_version`, `_dll_version`, `_unsafe`, `_locate`, `_state`) answer for the cases below.
windows/tests/PanelDeControl.Core.Tests/Upscalers must reach the same answers, in the same order. Rewrite it after a change with
`PYTHONPATH=py_modules python tests/test_upscalers_user_sources_parity.py --write`.
"""

import json
import sys
import types
from pathlib import Path

for _name in ("pwd", "fcntl"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

from upscalers import pe, user_deps, user_mods  # noqa: E402
from upscalers.recipe_catalog import DependencySpec  # noqa: E402

FIXTURE = Path(__file__).parents[1] / "shared" / "fixtures" / "upscalers" / "user_sources_parity.json"

PLUGIN = DependencySpec("puredark", "user_files", None, {"PDPerfPlugin.dll": "PDPerfPlugin.dll"}, None, None, (),
                        "UpscalerBasePlugin", "https://www.nexusmods.com/site/mods/502", "1.1.2", ("1.2.0",))
PAIR = DependencySpec("pair", "user_files", None, {"A.dll": "A.dll", "b.cfg": "B.cfg"}, None, None, (), "Pair", None, None, ())
UNVERSIONED = DependencySpec("free", "user_files", None, {"x.dll": "x.dll"}, None, None, (), "Free", None, None, ())

FILENAMES = [
    "UpscalerBasePlugin-502-1-1-2-1700000000.zip",
    "Mod-12-3-1700000001.7z",
    "Mod-12-3-4-5-6-1700000001.7z",
    "Mod-12-3-4-5-6-7-1700000001.7z",
    "ERSS-FG v4.14.rar",
    "plugin 1.2.0.zip",
    "plugin_v2.3.4.5.zip",
    "plugin-2.zip",
    "release 10.20.30.zip",
    "v1.1.2",
    "no version here.zip",
    "",
    "build1.2.zip",
    "Elden Ring - ERSS-FG - 1.0.zip",
]

VERSION_STRINGS = [
    {},
    {"FileVersion": "1.1.2.0"},
    {"FileVersion": "1, 1, 2, 0"},
    {"FileVersion": "", "ProductVersion": "2.0.1"},
    {"FileVersion": "n/a", "ProductVersion": "v3.4"},
    {"FileVersion": "1.2.3.4.5"},
    {"ProductVersion": "1.1.2 (release)"},
    {"FileVersion": "abc", "ProductVersion": "xyz"},
    {"FileVersion": "10.0.19041.1 (WinBuild.160101.0800)"},
]

MEMBERS = [
    "plugin.dll", "/etc/passwd", "\\abs.dll", "C:/a.dll", "a:b.dll", "../a.dll", "a/../b.dll", "a\\..\\b.dll",
    "-T/x.dll", "a/--x/y.dll", "a/b/c.dll", "Plugin [1.1.2]/PDPerfPlugin.dll", "a/-b", "a-b/c-d.dll", "..hidden/a",
]

LOCATE = [
    ("plugin", PLUGIN, "UpscalerBasePlugin-502-1-1-2-1.zip", ["UpscalerBasePlugin/PDPerfPlugin.dll", "readme.txt"]),
    ("plugin-backslash", PLUGIN, "x.zip", ["Plugin\\PDPerfPlugin.dll"]),
    ("plugin-other-case", PLUGIN, "x.zip", ["a/pdperfplugin.DLL"]),
    ("plugin-missing", PLUGIN, "x.zip", ["other.dll"]),
    ("plugin-twice", PLUGIN, "x.zip", ["a/PDPerfPlugin.dll", "b/PDPerfPlugin.dll"]),
    ("plugin-unsafe", PLUGIN, "x.zip", ["../PDPerfPlugin.dll"]),
    ("plugin-option-like", PLUGIN, "x.zip", ["-T/etc/PDPerfPlugin.dll"]),
    ("plugin-unsafe-beside-good", PLUGIN, "x.zip", ["PDPerfPlugin.dll", "a/--x/b.txt"]),
    ("loose-dll", PLUGIN, "PDPerfPlugin.dll", []),
    ("loose-dll-other-case", PLUGIN, "pdperfplugin.dll", []),
    ("loose-dll-wrong", PLUGIN, "other.dll", []),
    ("pair-both", PAIR, "x.7z", ["m/a.dll", "m/b.cfg"]),
    ("pair-one", PAIR, "x.7z", ["m/a.dll"]),
    ("pair-loose-dll", PAIR, "A.dll", []),
    ("pair-different-names", PAIR, "x.rar", ["B.CFG", "a.DLL"]),
    ("empty-archive", PLUGIN, "x.zip", []),
]

STATES = [
    (PLUGIN, "1.1.2"), (PLUGIN, "1.2.0"), (PLUGIN, "1.1.0"), (PLUGIN, None), (PLUGIN, "1.1.2.0"),
    (UNVERSIONED, "9.9"), (UNVERSIONED, None),
]

LAYOUTS = [
    ("flat", ["a.dll", "b.txt"], "Binaries/Win64", [], []),
    ("wrapper-dropped", ["ERSS-FG 1.2/a.dll", "ERSS-FG 1.2/b/c.dll"], "Binaries/Win64", [], []),
    ("wrapper-is-a-game-folder", ["Binaries/a.dll", "Binaries/b.dll"], "Binaries/Win64", [], ["Binaries"]),
    ("game-path-dropped", ["Binaries/Win64/a.dll", "Binaries/Win64/b/c.dll"], "Binaries/Win64", [], ["Binaries"]),
    ("wrapper-then-game-path", ["Mod/Binaries/Win64/a.dll", "Mod/Binaries/Win64/ERSS2/x.toml"], "Binaries/Win64", [], ["Binaries"]),
    ("game-path-other-case", ["binaries/win64/a.dll", "binaries/win64/b.dll"], "Binaries/Win64", [], ["Binaries"]),
    ("reaches-elsewhere", ["Binaries/Win64/a.dll", "Content/b.dll"], "Binaries/Win64", [], ["Binaries", "Content"]),
    ("reaches-a-game-folder-only", ["Content/b.dll", "a.dll"], "Binaries/Win64", [], ["Binaries", "Content"]),
    ("existing-folder-wrapper-kept", ["ERSS2/a.dll", "ERSS2/b.dll"], "Binaries/Win64", ["ERSS2"], []),
    ("existing-folder-case", ["erss2/a.dll", "ERSS2/b.dll"], "", ["ERSS2"], []),
    ("single-file-in-wrapper", ["Mod/a.dll"], "", [], []),
    ("single-file", ["a.dll"], "", [], []),
    ("exe-at-game-root", ["a.dll", "ERSS2/x.toml"], "", [], ["ERSS2"]),
    ("duplicate-after-dropping", ["a/x.dll", "x.dll"], "", [], []),
    ("duplicate-case", ["a.dll", "A.DLL"], "", [], []),
    ("backslashes", ["Mod\\a.dll", "Mod\\sub\\b.dll"], "", [], []),
    ("dot-segments", ["./a.dll", "./sub/./b.dll"], "", [], []),
    ("empty", [], "Binaries", [], []),
    ("deep-target", ["Game/Binaries/Win64/Shipping/a.dll", "Game/Binaries/Win64/Shipping/b.dll"], "Game/Binaries/Win64/Shipping", [], []),
    ("target-longer-than-member", ["Game/a.dll"], "Game/Binaries", [], ["Game"]),
    ("two-wrappers", ["A/x.dll", "B/y.dll"], "", [], []),
]

OPTISCALER = [
    ["a.dll"], ["OptiScaler.ini"], ["optiscaler.DLL"], ["OptiScaler/plugins/a.dll"], ["sub/OptiScaler.ini"], ["nvngx.dll"],
    ["nvngx_dlss.dll"], ["libxess.dll"], ["libxess_dx11.dll"], ["amd_fidelityfx_dx12.dll"], ["amd_fidelityfx_x.dll"],
    ["amdxcffx64.dll"], ["fakenvapi.dll"], ["fakenvapi.ini"], ["nvapi64.dll"], ["dlssg_to_fsr3_amd_is_better.dll"],
    ["D3D12_Optiscaler/D3D12Core.dll"], ["dxgi.dll", "ERSS2/ERSS-FG.toml"], ["ERSS2/nvngx.dll"], ["libxessx.dll.bak"],
    ["amd_fidelityfx.dll"], [],
]


def _error(call):
    try:
        return {"ok": call()}
    except user_mods.ModError as error:
        return {"error": error.code}
    except user_deps.UserFileError as error:
        return {"error": error.code}


def _locate(spec, name, members):
    original = user_deps._members
    user_deps._members = lambda _path: list(members)
    try:
        return _error(lambda: [[dest, member] for dest, member in user_deps._locate(spec, Path(name)).items()])
    finally:
        user_deps._members = original


def _dll_version(strings):
    original = pe.version_strings
    pe.version_strings = lambda _path: dict(strings)
    try:
        return user_deps._dll_version(Path("x.dll"))
    finally:
        pe.version_strings = original


def build():
    return {
        "filename_version": [{"name": name, "version": user_deps._filename_version(name)} for name in FILENAMES],
        "dll_version": [{"strings": strings, "version": _dll_version(strings)} for strings in VERSION_STRINGS],
        "unsafe": [{"member": member, "unsafe": user_deps._unsafe(member)} for member in MEMBERS],
        "locate": [{"name": label, "files": dict(spec.files), "file": file, "members": members,
                    "result": _locate(spec, file, members)} for label, spec, file, members in LOCATE],
        "state": [{"files": dict(spec.files), "required": spec.version, "avoid": list(spec.avoid_versions), "version": version,
                   "state": user_deps._state(spec, version)} for spec, version in STATES],
        "layout": [{"name": label, "members": members, "target": target, "existing": existing, "root_dirs": root_dirs,
                    "result": _error(lambda members=members, target=target, existing=existing, root_dirs=root_dirs: [
                        [destination, member] for destination, member in user_mods.layout(
                            members, target, set(existing), set(root_dirs)).items()])}
                   for label, members, target, existing, root_dirs in LAYOUTS],
        "replaces_optiscaler": [{"destinations": destinations, "replaces": user_mods.replaces_optiscaler(destinations)}
                                for destinations in OPTISCALER],
    }


def test_user_sources_match_the_shared_fixture():
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == json.loads(json.dumps(build()))


def test_fixture_covers_the_edge_cases():
    document = build()
    assert {entry["result"].get("error") for entry in document["layout"]} >= {None, "empty", "layout", "ambiguous_files"}
    assert {entry["result"].get("error") for entry in document["locate"]} >= {None, "missing_files", "ambiguous_files", "unsafe_archive"}
    assert {entry["state"] for entry in document["state"]} == {"ready", "avoid", "other_version"}
    assert any(entry["version"] is None for entry in document["filename_version"])
    assert any(entry["replaces"] for entry in document["replaces_optiscaler"])
    assert any(entry["unsafe"] for entry in document["unsafe"]) and any(not entry["unsafe"] for entry in document["unsafe"])


if __name__ == "__main__" and "--write" in sys.argv:
    with open(FIXTURE, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(build(), separators=(",", ":"), ensure_ascii=False) + "\n")
