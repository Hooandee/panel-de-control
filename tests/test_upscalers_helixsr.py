import io
import json
import zipfile
from pathlib import Path

import pytest

from upscalers import helixsr
from upscalers.helixsr import HelixError, HelixSR


def _write(path: Path, data: bytes | str = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


class Completed:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def _ready(home: Path) -> HelixSR:
    helix = HelixSR(str(home))
    _write(helix.release / "setup/helixsr_bridge.py", "")
    _write(helix.release / helixsr.COMPLETE, "ok")
    return helix


def test_bridge_runs_the_official_script_and_reads_its_json(tmp_path):
    helix = _ready(tmp_path)
    seen = []

    def run(argv, **kwargs):
        seen.append(argv)
        return Completed("note\n" + json.dumps({"protocol": 1, "ok": True, "version": "3.2.0", "network_ready": False}))

    helix.run = run
    status = helix.status()
    assert seen[0][-3:] == [str(helix.release / "setup/helixsr_bridge.py"), str(helix.release), "status"]
    assert status == {"downloaded": True, "version": "3.2.0", "network": False, "hlx": None}


def test_bridge_errors_carry_helixsrs_own_message(tmp_path):
    helix = _ready(tmp_path)
    helix.run = lambda argv, **kw: Completed(json.dumps({"ok": False, "error": "the network is not built yet"}), 1)
    with pytest.raises(HelixError) as error:
        helix.install(tmp_path / "game", "scaler")
    assert error.value.code == "helixsr_failed"
    assert error.value.detail == "the network is not built yet"


def test_scaler_install_points_at_the_bundled_helixsr_scaler(tmp_path):
    helix = _ready(tmp_path)
    seen = []

    def run(argv, **kwargs):
        seen.append(argv)
        return Completed(json.dumps({"ok": True, "game": {"installed": "scaler", "exe_folder": "/g/bin"}}))

    helix.run = run
    game = helix.install(tmp_path / "game", "scaler")
    assert game["installed"] == "scaler"
    argv = seen[0]
    assert argv[argv.index("--way") + 1] == "scaler"
    assert argv[argv.index("--scaler") + 1] == str(helix.release / "helixsr-scaler")
    assert argv[argv.index("--scaler-version") + 1] == helixsr.SCALER_VERSION


def test_nothing_runs_before_the_release_is_unpacked(tmp_path):
    helix = HelixSR(str(tmp_path))
    helix.run = lambda *a, **k: pytest.fail("must not run")
    assert helix.status() == {"downloaded": False}
    with pytest.raises(HelixError) as error:
        helix.remove(tmp_path / "game")
    assert error.value.code == "helixsr_missing"


def test_unpack_takes_only_the_release_folder(tmp_path):
    archive = tmp_path / "HelixSR.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr(f"{helixsr.RELEASE}/setup/helixsr_bridge.py", "")
        zipped.writestr(f"{helixsr.RELEASE}/HelixSR/helixsr.dll", "dll")
    archive.write_bytes(buffer.getvalue())
    helix = HelixSR(str(tmp_path / "home"))
    helix.unpack(archive)
    assert helix.ready()
    assert (helix.release / "HelixSR/helixsr.dll").read_text() == "dll"
    helix.unpack(archive)
    assert helix.ready()


def test_unpack_refuses_an_archive_without_the_bridge(tmp_path):
    archive = tmp_path / "HelixSR.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("something/else.txt", "")
    helix = HelixSR(str(tmp_path / "home"))
    with pytest.raises(HelixError) as error:
        helix.unpack(archive)
    assert error.value.code == "unpack_failed"
    assert not helix.ready()


class FakeProcess:
    def __init__(self, lines: list[str], code: int):
        self.stdout = io.StringIO("".join(f"{line}\n" for line in lines))
        self.code = code
        self.killed = False

    def wait(self, timeout=None):
        return self.code

    def kill(self):
        self.killed = True


def test_build_reports_each_setup_step_and_its_failure(tmp_path):
    helix = _ready(tmp_path)
    steps = []
    helix.popen = lambda argv, **kw: FakeProcess(
        ["[helixsr-setup] system: SteamOS", "[helixsr-setup] downloading nvngx_dlss.dll", "noise"], 1)
    with pytest.raises(HelixError) as error:
        helix.build(steps.append, lambda: False)
    assert steps == ["system: SteamOS", "downloading nvngx_dlss.dll"]
    assert error.value.code == "helixsr_build_failed"
    assert error.value.detail == "downloading nvngx_dlss.dll"


def test_build_stops_when_cancelled(tmp_path):
    helix = _ready(tmp_path)
    process = FakeProcess(["[helixsr-setup] downloading python.tar.gz", "[helixsr-setup] more"], 0)
    helix.popen = lambda argv, **kw: process
    with pytest.raises(HelixError) as error:
        helix.build(lambda step: None, lambda: True)
    assert error.value.code == "cancelled"
    assert process.killed


def test_log_proves_scaling_from_helixsrs_own_lines(tmp_path):
    exe = tmp_path / "Binaries"
    _write(exe / "HelixSR-fsrfg/helixsr.log",
           "[13:57:33.750] dispatch 1: render 640x360 -> 1280x720, jitter 0.219,0.179, mv scale 640.000,360.000\n")
    _write(exe / "OptiScaler.log", "[I] FFX upscaler: HLX DLSS (version name HelixSR (3.1.5), index 0)\n")
    facts = helixsr.read_log(exe, [exe / "HelixSR-fsrfg/helixsr.log"])
    assert facts["upscaler"] == "HLX DLSS"
    assert facts["resolution"] == {"render": [640, 360], "output": [1280, 720]}
    assert helixsr.verdict(facts) == "active"


def test_log_older_than_the_install_proves_nothing(tmp_path):
    log = _write(tmp_path / "helixsr.log", "dispatch 1: render 640x360 -> 1280x720\n")
    facts = helixsr.read_log(tmp_path, [log], since=log.stat().st_mtime + 10)
    assert helixsr.verdict(facts) == "not_run"


def test_hlx_fsr4_proves_itself_in_its_own_log(tmp_path):
    _write(tmp_path / "HLX_FSR.log",
           "[10:03:58.951000] [I] HLX-FSR-4 RADV: yes\n"
           "[10:03:59.458000] [I] HLX-FSR-4 own runtime active: int8p-s-std-k01 (tier 9), output 1280x800, "
           "max render 753x471, flags 0x19\n")
    facts = helixsr.read_log(tmp_path, [tmp_path / "helixsr.log"])
    assert facts["upscaler"] == "HLX FSR 4"
    assert facts["resolution"] == {"render": [753, 471], "output": [1280, 800]}
    assert helixsr.verdict(facts) == "active"
