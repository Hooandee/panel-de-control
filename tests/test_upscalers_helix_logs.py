import os

import pytest

from upscalers import diagnostics, helixsr
from upscalers.service import _facts


ACTIVE = "HLX-FSR-4 own runtime active: int8p-s-std-k01 (tier 9), output 1280x720, max render 1280x720\n"


def _log(path, modified, text=ACTIVE):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.utime(path, (modified, modified))
    return path


@pytest.mark.parametrize("fresh_first", [True, False])
def test_fresh_runtime_is_not_invalidated_by_stale_candidate(tmp_path, fresh_first):
    fresh = _log(tmp_path / "fresh" / "HLX_FSR.log", 101)
    stale = _log(tmp_path / "stale" / "HLX_FSR.log", 99)
    facts = helixsr.read_log([fresh, stale] if fresh_first else [stale, fresh], since=100)
    assert helixsr.verdict(facts) == "active"
    assert facts["path"] == str(fresh)


@pytest.mark.parametrize("modified, expected", [(99, "not_run"), (100, "active"), (101, "active")])
def test_helix_storage_runtime_obeys_install_timestamp(tmp_path, modified, expected):
    marker = _log(tmp_path / "helixsr-install.json", 100, "{}")
    _log(tmp_path / "_storage_" / "amd_fidelityfx_upscaler_dx12.dll", 100, "provider")
    runtime = _log(tmp_path / "_storage_" / "HLX_FSR.log", modified)
    install = {"engine": "helixsr", "target": str(tmp_path), "log": str(tmp_path / "helixsr.log"),
               "helix_file": str(marker), "installed_at": 100}
    facts = helixsr.read_install_log(install)
    assert helixsr.verdict(facts) == expected
    if expected == "active":
        assert facts["path"] == str(runtime)
        assert facts["output"] == [1280, 720]


@pytest.mark.parametrize("missing", ["engine", "installed_at", "marker", "provider"])
def test_storage_fallback_requires_helix_install_evidence(tmp_path, missing):
    marker = _log(tmp_path / "helixsr-install.json", 100, "{}")
    provider = _log(tmp_path / "_storage_" / "amd_fidelityfx_upscaler_dx12.dll", 100, "provider")
    _log(tmp_path / "_storage_" / "HLX_FSR.log", 101)
    install = {"engine": "helixsr", "target": str(tmp_path), "log": str(tmp_path / "helixsr.log"),
               "helix_file": str(marker), "installed_at": 100}
    if missing == "marker":
        marker.unlink()
    elif missing == "provider":
        provider.unlink()
    else:
        install.pop(missing)
    assert helixsr.verdict(helixsr.read_install_log(install)) == "not_run"


def test_verify_and_report_use_the_same_fresh_storage_log(tmp_path, monkeypatch):
    marker = _log(tmp_path / "helixsr-install.json", 100, "{}")
    _log(tmp_path / "_storage_" / "amd_fidelityfx_upscaler_dx12.dll", 100, "provider")
    _log(tmp_path / "HLX_FSR.log", 99, "old unrelated log")
    runtime = _log(tmp_path / "_storage_" / "HLX_FSR.log", 101)
    install = {"engine": "helixsr", "target": str(tmp_path), "log": str(tmp_path / "helixsr.log"),
               "helix_file": str(marker), "installed_at": 100}
    monkeypatch.setattr(diagnostics.games, "find_installed", lambda *_: None)
    monkeypatch.setattr(diagnostics, "_steam_config", lambda *_: {})
    report = diagnostics.game_report(str(tmp_path), "3764200", {"install": install})
    assert report["log_facts"] == _facts(install)
    assert report["log_verdict"] == "active"
    assert report["log_facts"]["path"] == str(runtime)
    assert report["log_excerpt"] == [ACTIVE.strip()]
