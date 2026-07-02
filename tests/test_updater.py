import importlib
import json
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def updater(monkeypatch):
    """updater.py imports `decky` at top level (for logging) and reads
    package.json/plugin.json relative to the plugin dir; inject a fake `decky`
    module before importing, then reload so the session cache starts clean."""
    fake = types.ModuleType("decky")
    fake.logger = types.SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None
    )
    monkeypatch.setitem(sys.modules, "decky", fake)
    monkeypatch.syspath_prepend(str(ROOT / "py_modules"))
    mod = importlib.reload(importlib.import_module("self_updater"))
    mod._cache = None  # ensure no leaked session cache between tests
    return mod


def test_is_newer_basic(updater):
    assert updater._is_newer("0.2.0", "0.1.0") is True
    assert updater._is_newer("0.1.0", "0.2.0") is False
    assert updater._is_newer("0.1.0", "0.1.0") is False
    assert updater._is_newer("1.0.0", "0.9.9") is True


def test_is_newer_strips_v_prefix(updater):
    assert updater._is_newer("v0.2.0", "0.1.0") is True
    assert updater._is_newer("V1.2.3", "v1.2.2") is True
    assert updater._is_newer("v1.0.0", "v1.0.0") is False


def test_is_newer_strips_dev_suffix(updater):
    # A -dev suffix on either side compares by the numeric core only.
    assert updater._is_newer("0.2.0-dev.abc123", "0.1.0") is True
    assert updater._is_newer("0.2.0-dev.abc123", "0.2.0") is False
    assert updater._is_newer("v0.2.0", "0.2.0-dev.xyz") is False


def test_shape_selects_panel_de_control_zip(updater, monkeypatch):
    # plugin.json "name" == the zip asset base name the installer picks.
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    data = {
        "tag_name": "v0.2.0",
        "body": "Changelog here",
        "assets": [
            {"name": "other.zip", "browser_download_url": "https://x/other.zip"},
            {
                "name": "Panel de Control.zip",
                "browser_download_url": "https://x/Panel%20de%20Control.zip",
            },
        ],
    }
    result = updater._shape(data, current="0.1.0")
    assert result["download_url"] == "https://x/Panel%20de%20Control.zip"
    assert result["latest"] == "0.2.0"
    assert result["has_update"] is True


def test_shape_no_matching_asset_means_no_update(updater, monkeypatch):
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    data = {
        "tag_name": "v0.2.0",
        "body": "",
        "assets": [{"name": "wrong.zip", "browser_download_url": "https://x/wrong.zip"}],
    }
    result = updater._shape(data, current="0.1.0")
    assert result["download_url"] == ""
    # No downloadable asset → not an actionable update.
    assert result["has_update"] is False


def test_check_shapes_mocked_release_json(updater, monkeypatch):
    monkeypatch.setattr(updater, "read_version", lambda: "0.1.0")
    monkeypatch.setattr(updater, "_repo_slug", lambda: "panel-de-control")
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    payload = {
        "tag_name": "v0.2.0",
        "body": "New in 0.2.0",
        "assets": [
            {
                "name": "Panel de Control.zip",
                "browser_download_url": "https://gh/Panel%20de%20Control.zip",
            }
        ],
    }
    monkeypatch.setattr(updater, "_http_get", lambda url, accept: json.dumps(payload).encode())

    result = updater.check(force=True)
    assert result == {
        "current": "0.1.0",
        "latest": "0.2.0",
        "notes": "New in 0.2.0",
        "download_url": "https://gh/Panel%20de%20Control.zip",
        "has_update": True,
        "error": "",
    }


def test_check_network_failure_returns_error_status(updater, monkeypatch):
    monkeypatch.setattr(updater, "read_version", lambda: "0.1.0")
    monkeypatch.setattr(updater, "_repo_slug", lambda: "panel-de-control")

    def boom(url, accept):
        raise OSError("no network")

    monkeypatch.setattr(updater, "_http_get", boom)

    result = updater.check(force=True)
    # Never raises; reports a status the UI can render.
    assert result["error"] == "network"
    assert result["has_update"] is False
    assert result["current"] == "0.1.0"


def test_check_caches_per_session(updater, monkeypatch):
    monkeypatch.setattr(updater, "read_version", lambda: "0.1.0")
    monkeypatch.setattr(updater, "_repo_slug", lambda: "panel-de-control")
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    calls = {"n": 0}

    def counting_get(url, accept):
        calls["n"] += 1
        return json.dumps({"tag_name": "v0.1.0", "body": "", "assets": []}).encode()

    monkeypatch.setattr(updater, "_http_get", counting_get)

    updater.check(force=True)
    updater.check(force=False)  # served from the session cache
    assert calls["n"] == 1


def test_extract_semver_release_please_component_tag(updater):
    # release-please tags this repo as "<package>-v<semver>", not "v<semver>".
    assert updater._extract_semver("panel-de-control-v0.2.0") == "0.2.0"
    assert updater._extract_semver("v1.2.3") == "1.2.3"
    assert updater._extract_semver("1.2.3") == "1.2.3"
    assert updater._extract_semver("no-semver-here") == ""


def test_is_newer_component_tag(updater):
    assert updater._is_newer("panel-de-control-v0.2.0", "0.1.0") is True
    assert updater._is_newer("panel-de-control-v0.1.0", "0.1.0") is False


def test_shape_component_tag(updater, monkeypatch):
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    data = {
        "tag_name": "panel-de-control-v0.2.0",
        "body": "notes",
        "assets": [
            {
                "name": "Panel de Control.zip",
                "browser_download_url": "https://x/Panel%20de%20Control.zip",
            }
        ],
    }
    result = updater._shape(data, current="0.1.0")
    assert result["latest"] == "0.2.0"
    assert result["has_update"] is True


def test_shape_matches_github_dotted_asset_name(updater, monkeypatch):
    # GitHub replaces spaces with dots: "Panel de Control.zip" -> "Panel.de.Control.zip".
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    data = {
        "tag_name": "panel-de-control-v0.2.0",
        "body": "",
        "assets": [
            {"name": "Panel.de.Control.zip", "browser_download_url": "https://x/Panel.de.Control.zip"},
        ],
    }
    result = updater._shape(data, current="0.1.0")
    assert result["download_url"] == "https://x/Panel.de.Control.zip"
    assert result["has_update"] is True


def test_check_404_is_benign(updater, monkeypatch):
    import urllib.error

    monkeypatch.setattr(updater, "read_version", lambda: "0.1.0")
    monkeypatch.setattr(updater, "_repo_slug", lambda: "panel-de-control")

    def not_found(url, accept):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(updater, "_http_get", not_found)
    result = updater.check(force=True)
    # No published release yet is benign — up to date, no error toast.
    assert result["error"] == ""
    assert result["has_update"] is False
    assert result["latest"] == "0.1.0"
