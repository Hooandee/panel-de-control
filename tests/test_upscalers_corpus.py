"""Escaladores regression corpus: the plan for every captured game must stay exactly as reviewed.

Each machine under tests/fixtures/upscalers_corpus/ is a captured game library (metadata only). The backend runs
on a fake copy of it and the result is compared with golden/<machine>.json. A change that moves any game's
plan (chosen exe, detected inputs, files written, INI keys, overrides, launch options, Mako key) fails here,
naming the game and the field. When the change is intended, regenerate and review the golden diff:

    UPSCALERS_CORPUS_UPDATE=1 python -m pytest tests/test_upscalers_corpus.py
"""

import json
import os
from pathlib import Path

import pytest

from upscalers import games, pe
from upscalers_corpus_plan import dump, golden_path, machine_plan
from upscalers_corpus_tree import load, machines, pe_image, shortcuts_vdf, write_file
from steam_cleaner import vdf

UPDATE = os.environ.get("UPSCALERS_CORPUS_UPDATE") == "1"
MAX_REPORTED = 40


def _differences(expected, actual, path=""):
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            where = f"{path}.{key}" if path else str(key)
            if key not in actual:
                yield where, expected[key], "<missing>"
            elif key not in expected:
                yield where, "<missing>", actual[key]
            else:
                yield from _differences(expected[key], actual[key], where)
    elif isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        for index, (left, right) in enumerate(zip(expected, actual)):
            yield from _differences(left, right, f"{path}[{index}]")
    elif expected != actual:
        yield path, expected, actual


def _short(value) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return text if len(text) <= 160 else text[:157] + "..."


@pytest.mark.parametrize("machine", machines())
def test_every_captured_game_keeps_its_plan(machine, tmp_path):
    plan = json.loads(dump(machine_plan(tmp_path, load(machine))))
    golden = golden_path(machine)
    if UPDATE:
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(dump(plan), encoding="utf-8")
        return
    assert golden.is_file(), f"no golden plan for {machine}: run with UPSCALERS_CORPUS_UPDATE=1 and review it"
    expected = json.loads(golden.read_text(encoding="utf-8"))
    changes = []
    for appid in sorted(set(expected) | set(plan)):
        name = (plan.get(appid) or expected.get(appid) or {}).get("name")
        for where, before, after in _differences(expected.get(appid), plan.get(appid)):
            changes.append(f"{machine} {appid} {name!r} {where}: {_short(before)} -> {_short(after)}")
    if changes:
        shown = "\n".join(changes[:MAX_REPORTED])
        more = f"\n... and {len(changes) - MAX_REPORTED} more" if len(changes) > MAX_REPORTED else ""
        pytest.fail(f"{len(changes)} plan change(s); if intended, regenerate with UPSCALERS_CORPUS_UPDATE=1 "
                    f"and review the golden diff:\n{shown}{more}", pytrace=False)


@pytest.mark.parametrize("machine", machines())
def test_capture_has_no_personal_paths(machine):
    text = (Path(__file__).parent / "fixtures" / "upscalers_corpus" / f"{machine}.json").read_text(encoding="utf-8")
    assert "/home/" not in text.replace("/home/USER", "")
    assert "/run/media/" not in text.replace("/run/media/USER", "")
    assert '"userdata/' not in text or "userdata/0" in text


def test_fake_executable_reads_back_like_the_original(tmp_path):
    exe = tmp_path / "Game-Win64-Shipping.exe"
    write_file(exe, 300 * 1024 * 1024, {
        "imports": ["d3d12.dll", "dxgi.dll", "kernel32.dll"], "embedded": ["fsr31", "xess"],
        "version": {"ProductName": "Game", "FileVersion": "1.2.3.4", "OriginalFilename": "v2.14.1"}})
    assert pe.imported_dlls(str(exe)) == {"d3d12.dll", "dxgi.dll", "kernel32.dll"}
    assert pe.graphics_apis(str(exe)) == ["d3d12", "dxgi"]
    assert pe.version_strings(str(exe)) == {"ProductName": "Game", "FileVersion": "1.2.3.4", "OriginalFilename": "v2.14.1"}
    assert games.embedded_upscalers(exe) == {"fsr31", "xess"}
    assert exe.stat().st_size == 300 * 1024 * 1024
    assert pe.imported_dlls(str(_written(tmp_path / "empty.dll", pe_image([], {})))) == set()


def test_fake_shortcuts_file_reads_back(tmp_path):
    path = _written(tmp_path / "shortcuts.vdf", shortcuts_vdf([
        {"appid": "3221789842", "appname": "Game", "exe": '"/games/Game.exe"', "startdir": '"/games"', "launchoptions": "-dx12"}]))
    entry = vdf.read_shortcuts(path)["0"]
    assert (str(entry["appid"]), entry["appname"], entry["exe"], entry["startdir"], entry["launchoptions"]) == (
        "3221789842", "Game", '"/games/Game.exe"', '"/games"', "-dx12")


def _written(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path
