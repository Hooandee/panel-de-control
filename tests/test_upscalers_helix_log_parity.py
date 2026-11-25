"""HLX_FSR.log verdicts shared with the Windows port.

`shared/fixtures/upscalers/helix_logs.json` records what `upscalers.helixsr` reads from each set of files below: the
facts and the verdict, for a list of candidate logs and for a whole Panel install. The C# reader in
windows/tests/PanelDeControl.Core.Tests/Upscalers must reach the same answers. Rewrite it after a change with
`PYTHONPATH=py_modules python tests/test_upscalers_helix_log_parity.py --write`.
"""

import importlib
import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "shared" / "fixtures" / "upscalers" / "helix_logs.json"
MTIME = 1_700_000_000


def _load_helixsr():
    try:
        from upscalers import helixsr
        return helixsr
    except ImportError:
        pass
    # Windows has no pwd or fcntl, which the rest of the package imports; helixsr itself only needs these two.
    package = types.ModuleType("_helix_probe")
    package.__path__ = [str(ROOT / "py_modules" / "upscalers")]
    session = types.ModuleType("user_session")
    session.session_for_uid = session.spawn_args = lambda *args, **kwargs: None
    ownership = types.ModuleType("_helix_probe.ownership")
    ownership.own_like = lambda *args, **kwargs: None
    saved = {name: sys.modules.get(name) for name in ("_helix_probe", "_helix_probe.ownership", "user_session")}
    sys.modules.update({"_helix_probe": package, "_helix_probe.ownership": ownership, "user_session": session})
    try:
        return importlib.import_module("_helix_probe.helixsr")
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


helixsr = _load_helixsr()

ACTIVE = "HLX-FSR-4 own runtime active: int8p-s-std-k01 (tier 9), output 1280x720, max render 1280x720\n"
ACTIVE_LATER = "HLX-FSR-4 own runtime active: int8p-s-std-k01 (tier 9), output 2560x1440, max render 1920x1080\n"
LOADED = "[HelixSR] loaded\nHLX-FSR-4 starting\n"
SHORT = "HLX-FSR-4 own runtime active: tier 9, output 5x5, max render 5x5\n"
NOISE = "garbage \xe9 中\nHLX-FSR-4 own runtime active: x output 3840x2160, max render 3840x2160\r\n"


def _file(text, mtime=MTIME, lead=0, pad=0):
    return {"text": text, "mtime": mtime, "lead": lead, "pad": pad}


READ_CASES = [
    {"name": "no-log", "files": {}, "logs": ["helixsr.log"]},
    {"name": "loaded-only", "files": {"helixsr.log": _file(LOADED)}, "logs": ["helixsr.log"]},
    {"name": "active-in-own-log", "files": {"helixsr.log": _file(ACTIVE)}, "logs": ["helixsr.log"]},
    {"name": "active-in-sibling-runtime-log", "files": {"a/helixsr.log": _file(LOADED), "a/HLX_FSR.log": _file(ACTIVE)},
     "logs": ["a/helixsr.log"]},
    {"name": "last-context-wins", "files": {"HLX_FSR.log": _file(ACTIVE + ACTIVE_LATER)}, "logs": ["helixsr.log"]},
    {"name": "output-too-short", "files": {"helixsr.log": _file(SHORT)}, "logs": ["helixsr.log"]},
    {"name": "undecodable-bytes-and-crlf", "files": {"helixsr.log": _file(NOISE)}, "logs": ["helixsr.log"]},
    {"name": "stale-log", "files": {"helixsr.log": _file(ACTIVE, MTIME - 1)}, "logs": ["helixsr.log"], "since": MTIME},
    {"name": "log-written-at-install", "files": {"helixsr.log": _file(ACTIVE)}, "logs": ["helixsr.log"], "since": MTIME},
    {"name": "fresh-after-stale", "files": {"s/HLX_FSR.log": _file(ACTIVE_LATER, MTIME - 5), "f/HLX_FSR.log": _file(ACTIVE, MTIME + 5)},
     "logs": ["s/HLX_FSR.log", "f/HLX_FSR.log"], "since": MTIME},
    {"name": "stale-after-fresh", "files": {"s/HLX_FSR.log": _file(ACTIVE_LATER, MTIME - 5), "f/HLX_FSR.log": _file(ACTIVE, MTIME + 5)},
     "logs": ["f/HLX_FSR.log", "s/HLX_FSR.log"], "since": MTIME},
    {"name": "stale-own-fresh-sibling", "files": {"helixsr.log": _file(LOADED, MTIME - 5), "HLX_FSR.log": _file(ACTIVE, MTIME + 5)},
     "logs": ["helixsr.log"], "since": MTIME},
    {"name": "context-cut-by-the-size-limit", "files": {"HLX_FSR.log": _file(ACTIVE, pad=2_500_000)}, "logs": ["helixsr.log"]},
    {"name": "context-kept-inside-the-size-limit", "files": {"HLX_FSR.log": _file(ACTIVE, lead=2_500_000)}, "logs": ["helixsr.log"]},
    {"name": "no-candidates", "files": {"HLX_FSR.log": _file(ACTIVE)}, "logs": []},
]

PROVIDER = "_storage_/amd_fidelityfx_upscaler_dx12.dll"
RUNTIME = "_storage_/HLX_FSR.log"
MARKER = "bin/helixsr-install.json"


def _install_files(modified=MTIME + 1, **missing):
    files = {MARKER: _file("{}"), PROVIDER: _file("provider"), RUNTIME: _file(ACTIVE, modified), "bin/helixsr.log": _file(LOADED)}
    for name in missing:
        files.pop({"marker": MARKER, "provider": PROVIDER, "runtime": RUNTIME}[name], None)
    return files


def _install(**overrides):
    return {"engine": "helixsr", "target": ".", "log": "bin/helixsr.log", "helix_file": MARKER, "installed_at": MTIME, **overrides}


INSTALL_CASES = [
    {"name": "storage-runtime-fresh", "files": _install_files(), "install": _install()},
    {"name": "storage-runtime-at-install-time", "files": _install_files(MTIME), "install": _install()},
    {"name": "storage-runtime-before-install", "files": _install_files(MTIME - 1), "install": _install()},
    {"name": "no-marker", "files": _install_files(marker=True), "install": _install()},
    {"name": "no-provider", "files": _install_files(provider=True), "install": _install()},
    {"name": "no-install-time", "files": _install_files(), "install": _install(installed_at=None)},
    {"name": "other-engine", "files": _install_files(), "install": _install(engine="optiscaler")},
    {"name": "no-log-path", "files": _install_files(), "install": _install(log=None)},
    {"name": "no-storage-runtime", "files": _install_files(runtime=True), "install": _install()},
]


def _write(folder: Path, files: dict) -> None:
    for name, item in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        filler = b"x\n" * 1_250_000
        path.write_bytes(filler[:item["lead"]] + item["text"].encode("utf-8") + filler[:item["pad"]])
        os.utime(path, (item["mtime"], item["mtime"]))


def _facts(facts: dict, folder: Path) -> dict:
    result = {key: value for key, value in facts.items() if key != "path"}
    if "path" in facts:
        result["path"] = Path(facts["path"]).relative_to(folder).as_posix()
    return result


def _expected(case: dict) -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary).resolve()
        _write(folder, case["files"])
        if "install" in case:
            install = {key: value for key, value in case["install"].items() if value is not None}
            for key in ("log", "helix_file"):
                if key in install:
                    install[key] = str(folder / install[key])
            install["target"] = str(folder)
            facts = helixsr.read_install_log(install)
        else:
            facts = helixsr.read_log([folder / name for name in case["logs"]], since=case.get("since"))
        return {"facts": _facts(facts, folder), "verdict": helixsr.verdict(facts)}


def snapshot() -> dict:
    return json.loads(json.dumps({
        "schema_version": 1,
        "mtime": MTIME,
        "read": [{**case, "expected": _expected(case)} for case in READ_CASES],
        "install": [{**case, "expected": _expected(case)} for case in INSTALL_CASES],
    }))


def test_fixture_matches_the_linux_backend():
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == snapshot()


def test_cases_cover_every_verdict():
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    verdicts = {case["expected"]["verdict"] for case in document["read"] + document["install"]}
    assert verdicts == {"not_run", "loaded", "active"}


if __name__ == "__main__" and "--write" in sys.argv:
    FIXTURE.write_text(json.dumps(snapshot(), separators=(",", ":"), ensure_ascii=True) + "\n", encoding="utf-8")
