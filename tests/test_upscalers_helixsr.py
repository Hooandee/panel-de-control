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


def test_bridge_errors_carry_helixsrs_own_message(tmp_path):
    helix = _ready(tmp_path)
    helix.run = lambda argv, **kw: Completed(json.dumps({"ok": False, "error": "the network is not built yet"}), 1)
    with pytest.raises(HelixError) as error:
        helix.install(tmp_path / "game")
    assert error.value.code == "helixsr_failed"
    assert error.value.detail == "the network is not built yet"


def test_nothing_runs_before_the_release_is_unpacked(tmp_path):
    helix = HelixSR(str(tmp_path))
    helix.run = lambda *a, **k: pytest.fail("must not run")
    assert not helix.ready()
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


def test_log_older_than_the_install_proves_nothing(tmp_path):
    log = _write(tmp_path / "helixsr.log", "dispatch 1: render 640x360 -> 1280x720\n")
    facts = helixsr.read_log([log], since=log.stat().st_mtime + 10)
    assert helixsr.verdict(facts) == "not_run"


def test_hlx_fsr4_proves_itself_in_its_own_log(tmp_path):
    _write(tmp_path / "HLX_FSR.log",
           "[10:03:58.951000] [I] HLX-FSR-4 RADV: yes\n"
           "[10:03:59.458000] [I] HLX-FSR-4 own runtime active: int8p-s-std-k01 (tier 9), output 1280x800, "
           "max render 1280x800, flags 0x19\n")
    facts = helixsr.read_log([tmp_path / "helixsr.log"])
    assert facts["upscaler"] == "HLX FSR 4"
    assert facts["output"] == [1280, 800]
    assert "resolution" not in facts
    assert helixsr.verdict(facts) == "active"


def test_forget_drops_only_a_backup_identical_to_the_games_file(tmp_path):
    _write(tmp_path / "helixsr-install.json", json.dumps({"files": ["a.dll", "b.dll", "../c.dll"]}))
    _write(tmp_path / "a.dll", b"game update")
    _write(tmp_path / "a.original.dll", b"game update")
    _write(tmp_path / "b.dll", b"game update")
    _write(tmp_path / "b.original.dll", b"older game")
    helixsr.forget(tmp_path)
    assert not (tmp_path / "a.original.dll").exists()
    assert (tmp_path / "b.original.dll").read_bytes() == b"older game"
    assert (tmp_path / "a.dll").read_bytes() == b"game update"
    assert not (tmp_path / "helixsr-install.json").exists()
