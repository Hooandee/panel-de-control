"""OptiScaler.ini facts of a support report shared with the Windows port.

`shared/fixtures/upscalers/ini_diagnostics.json` records what `diagnostics.ini_values`, `ini_drift` and `ini_request`
answer for the cases below. windows/tests/PanelDeControl.Core.Tests/Upscalers must reach the same answers, in the same
order. Rewrite it after a change with `PYTHONPATH=py_modules python tests/test_upscalers_diagnostics_parity.py --write`.
"""

import json
import sys
import tempfile
import types
from pathlib import Path

for _name in ("pwd", "fcntl"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

from upscalers import diagnostics  # noqa: E402

FIXTURE = Path(__file__).parents[1] / "shared" / "fixtures" / "upscalers" / "ini_diagnostics.json"

INI = """[Upscalers]
; Select upscaler for DX12 games
Dx12Upscaler=fsr31
;Dx11Upscaler=ignored
Dx11Upscaler = xess

[FSR]
Fsr4Model=1
Fsr4Update=true
Fsr4Update=false

[Tweaks]
; Overlay position
; a, b, c - Default (auto) is a
Position=b
Scale=1.5
Note=not a number

[Log]
LogLevel=2
"""

CASES = [
    {"id": "reported_keys_only", "text": INI, "extra": []},
    {"id": "edited_keys_are_added", "text": INI, "extra": ["Tweaks.Scale", "Tweaks.Missing"]},
    {"id": "long_value_is_cut", "text": "[Log]\nLogLevel=" + "9" * 200 + "\n", "extra": []},
    {"id": "missing_file", "text": None, "extra": []},
]

DRIFT = [
    {"id": "unrecorded", "written": None, "text": INI, "edited": {}},
    {"id": "missing", "written": {"at": 5, "values": {"Log.LogLevel": "2"}}, "text": None, "edited": {}},
    {"id": "as_written", "written": {"at": 5, "values": {"Log.LogLevel": "2", "Tweaks.Scale": "1.5"}}, "text": INI, "edited": {"Tweaks.Scale": "1.5"}},
    {"id": "changed_and_gone", "written": {"at": 5, "values": {"Log.LogLevel": "3", "Tweaks.Scale": "1.5", "Spoofing.Dxgi": "true"}}, "text": INI,
     "edited": {"Tweaks.Scale": "1.5"}},
]

REQUESTS = [
    ("Tweaks.Scale", "1.5"), ("Scale", "2"), ("Position", "b"), ("Position", "zzz"), ("Tweaks.Note", "not a number"),
    ("Nope", "1"), ("Log.LogLevel", "auto"), ("Tweaks.Position", "-3.25"),
]


def _values(case) -> dict:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "OptiScaler.ini"
        if case["text"] is not None:
            path.write_text(case["text"], encoding="utf-8")
        result = diagnostics.ini_values(path, case["extra"])
    return {"missing": True} if result.get("missing") else {"values": [[key, value] for key, value in result.items()]}


def _drift(case) -> dict:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "OptiScaler.ini"
        if case["text"] is not None:
            path.write_text(case["text"], encoding="utf-8")
        install = {"edited": case["edited"]}
        if case["written"]:
            install["ini_written"] = case["written"]
        result = diagnostics.ini_drift(install, path)
    return {"status": result["status"], "written_at": result.get("written_at"),
            "keys": [[key, item["panel"], item["now"]] for key, item in result.get("keys", {}).items()]}


def _requests() -> list:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "OptiScaler.ini"
        path.write_text(INI, encoding="utf-8")
        return [{"key": key, "value": value, "expected": diagnostics.ini_request(path, key, value)} for key, value in REQUESTS]


def snapshot() -> dict:
    return json.loads(json.dumps({
        "schema_version": 1,
        "ini": INI,
        "values": [{**case, "expected": _values(case)} for case in CASES],
        "drift": [{**case, "expected": _drift(case)} for case in DRIFT],
        "requests": _requests(),
    }))


def test_fixture_matches_the_linux_backend():
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == snapshot()


def test_cases_cover_what_a_report_distinguishes():
    data = snapshot()
    assert {item["expected"]["status"] for item in data["drift"]} == {"unrecorded", "missing", "as_written", "changed"}
    assert any("value" in item["expected"] for item in data["requests"])
    assert any(item["expected"].get("value_omitted") for item in data["requests"])
    assert any(item["expected"].get("missing") for item in data["values"])


if __name__ == "__main__" and "--write" in sys.argv:
    FIXTURE.write_text(json.dumps(snapshot(), separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
