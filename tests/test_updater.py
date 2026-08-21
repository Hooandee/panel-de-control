import functools
import importlib
import io
import json
import pathlib
import sys
import threading
import time
import types
import urllib.error
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _release(
    version,
    body="",
    *,
    asset_url="",
    draft=False,
    prerelease=False,
):
    assets = []
    if asset_url:
        assets.append(
            {
                "name": "Panel.de.Control.zip",
                "browser_download_url": asset_url,
            }
        )
    return {
        "tag_name": f"v{version}",
        "body": body,
        "draft": draft,
        "prerelease": prerelease,
        "assets": assets,
    }


def _release_archive(version):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as release_zip:
        release_zip.writestr(
            "Panel de Control/package.json",
            json.dumps({"version": version}),
        )
    return archive.getvalue()


def _cached_package_version(package):
    @functools.lru_cache(maxsize=1)
    def read():
        return json.loads(package.read_text(encoding="utf-8"))["version"]

    return read


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
    payload = [_release("0.2.0", "New in 0.2.0", asset_url="https://gh/update.zip")]

    def release_get(url, accept):
        data = payload[0] if url.endswith("/latest") else payload
        return json.dumps(data).encode()

    monkeypatch.setattr(updater, "_http_get", release_get)

    result = updater.check(force=True)
    assert result == {
        "current": "0.1.0",
        "latest": "0.2.0",
        "notes": "## v0.2.0\n\nNew in 0.2.0",
        "download_url": "https://gh/update.zip",
        "has_update": True,
        "error": "",
    }


def test_check_collects_every_stable_release_after_current(updater, monkeypatch):
    monkeypatch.setattr(updater, "read_version", lambda: "0.2.0")
    monkeypatch.setattr(updater, "_repo_slug", lambda: "panel-de-control")
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    latest = _release("0.4.0", "Latest changes", asset_url="https://gh/update.zip")
    payload = [
        _release("0.3.0", "Earlier changes"),
        _release("0.6.0", "Not the published latest"),
        _release("0.5.0", "Preview", prerelease=True),
        _release("0.4.1", "Draft", draft=True),
        latest,
        _release("0.3.0", "Duplicate changes"),
        _release("0.2.0", "Already installed"),
    ]

    def release_get(url, accept):
        data = latest if url.endswith("/latest") else payload
        return json.dumps(data).encode()

    monkeypatch.setattr(updater, "_http_get", release_get)

    result = updater.check(force=True)

    assert result["latest"] == "0.4.0"
    assert result["download_url"] == "https://gh/update.zip"
    assert result["has_update"] is True
    assert result["notes"] == (
        "## v0.4.0\n\nLatest changes\n\n"
        "## v0.3.0\n\nEarlier changes"
    )


def test_check_reads_every_release_page(updater, monkeypatch):
    monkeypatch.setattr(updater, "read_version", lambda: "0.1.0")
    monkeypatch.setattr(updater, "_repo_slug", lambda: "panel-de-control")
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    installed = _release("0.1.0", "Installed")
    latest = _release("0.2.0", "Next page", asset_url="https://gh/update.zip")
    intermediate = _release("0.1.5", "Only on page two")
    requested = []

    def paged_get(url, accept):
        requested.append(url)
        if url.endswith("/latest"):
            return json.dumps(latest).encode()
        payload = [latest, intermediate] if "page=2" in url else [installed] * 100
        return json.dumps(payload).encode()

    monkeypatch.setattr(updater, "_http_get", paged_get)

    result = updater.check(force=True)

    assert requested == [
        "https://api.github.com/repos/Hooandee/panel-de-control/releases/latest",
        "https://api.github.com/repos/Hooandee/panel-de-control/releases?per_page=100&page=1",
        "https://api.github.com/repos/Hooandee/panel-de-control/releases?per_page=100&page=2",
    ]
    assert result["latest"] == "0.2.0"
    assert result["notes"] == (
        "## v0.2.0\n\nNext page\n\n"
        "## v0.1.5\n\nOnly on page two"
    )


def test_check_keeps_latest_notes_when_release_history_is_empty(updater, monkeypatch):
    monkeypatch.setattr(updater, "read_version", lambda: "0.1.0")
    monkeypatch.setattr(updater, "_repo_slug", lambda: "panel-de-control")
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    latest = _release("0.2.0", "Latest changes", asset_url="https://gh/update.zip")

    def release_get(url, accept):
        return json.dumps(latest if url.endswith("/latest") else []).encode()

    monkeypatch.setattr(updater, "_http_get", release_get)

    result = updater.check(force=True)

    assert result["notes"] == "## v0.2.0\n\nLatest changes"


def test_check_discards_partial_update_when_release_history_fails(updater, monkeypatch):
    monkeypatch.setattr(updater, "read_version", lambda: "0.1.0")
    monkeypatch.setattr(updater, "_repo_slug", lambda: "panel-de-control")
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    latest = _release("0.2.0", "Latest changes", asset_url="https://gh/update.zip")

    def release_get(url, accept):
        if url.endswith("/latest"):
            return json.dumps(latest).encode()
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(updater, "_http_get", release_get)

    result = updater.check(force=True)

    assert result["error"] == "network"
    assert result["has_update"] is False
    assert result["download_url"] == ""


def test_check_coalesces_concurrent_session_requests(updater, monkeypatch):
    monkeypatch.setattr(updater, "read_version", lambda: "0.1.0")
    monkeypatch.setattr(updater, "_repo_slug", lambda: "panel-de-control")
    calls = 0
    calls_lock = threading.Lock()
    start = threading.Barrier(2)

    def release_get(url, accept):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return json.dumps(_release("0.1.0")).encode()

    def check():
        start.wait()
        return updater.check()

    monkeypatch.setattr(updater, "_http_get", release_get)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: check(), range(2)))

    assert calls == 1
    assert results[0] == results[1]


def test_install_serializes_forced_checks_and_refreshes_cached_version(
    updater, monkeypatch, tmp_path
):
    plugin_dir = tmp_path / "Panel de Control"
    plugin_dir.mkdir()
    package = plugin_dir / "package.json"
    package.write_text(json.dumps({"version": "0.1.0"}), encoding="utf-8")
    archive = _release_archive("0.2.0")

    installed_asset = "https://gh/0.2.0.zip"
    next_release = _release(
        "0.3.0",
        "Next release",
        asset_url="https://gh/0.3.0.zip",
    )
    updater._cache = {
        "current": "0.1.0",
        "latest": "0.2.0",
        "notes": "## v0.2.0",
        "download_url": installed_asset,
        "has_update": True,
        "error": "",
    }
    download_started = threading.Event()
    release_download = threading.Event()
    forced_check_started = threading.Event()
    asset_downloads = 0

    def release_get(url, accept):
        nonlocal asset_downloads
        if url == installed_asset:
            asset_downloads += 1
            download_started.set()
            assert release_download.wait(timeout=1)
            return archive
        forced_check_started.set()
        payload = next_release if url.endswith("/latest") else [next_release]
        return json.dumps(payload).encode()

    monkeypatch.setattr(updater, "_http_get", release_get)
    monkeypatch.setattr(updater, "_plugin_dir", lambda: plugin_dir)
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    monkeypatch.setattr(updater, "_repo_slug", lambda: "panel-de-control")

    cached_version = _cached_package_version(package)
    assert cached_version() == "0.1.0"
    monkeypatch.setattr(updater, "read_version", cached_version)

    with ThreadPoolExecutor(max_workers=2) as pool:
        install_result = pool.submit(updater.install)
        assert download_started.wait(timeout=1)
        check_result = pool.submit(updater.check, True)
        overlapped = forced_check_started.wait(timeout=0.05)
        release_download.set()
        installed = install_result.result(timeout=1)
        checked = check_result.result(timeout=1)

    assert overlapped is False
    assert forced_check_started.is_set() is True
    assert installed["ok"] is True
    assert checked["current"] == "0.2.0"
    assert checked["latest"] == "0.3.0"
    assert checked["has_update"] is True
    assert updater._cache == checked
    assert cached_version() == "0.2.0"
    assert asset_downloads == 1


def test_concurrent_install_requests_download_once(updater, monkeypatch, tmp_path):
    plugin_dir = tmp_path / "Panel de Control"
    plugin_dir.mkdir()
    package = plugin_dir / "package.json"
    package.write_text(json.dumps({"version": "0.1.0"}), encoding="utf-8")
    archive = _release_archive("0.2.0")

    asset_url = "https://gh/0.2.0.zip"
    updater._cache = {
        "current": "0.1.0",
        "latest": "0.2.0",
        "notes": "## v0.2.0",
        "download_url": asset_url,
        "has_update": True,
        "error": "",
    }
    download_started = threading.Event()
    release_download = threading.Event()
    downloads = 0

    def release_get(url, accept):
        nonlocal downloads
        assert url == asset_url
        downloads += 1
        download_started.set()
        assert release_download.wait(timeout=1)
        return archive

    cached_version = _cached_package_version(package)
    assert cached_version() == "0.1.0"
    monkeypatch.setattr(updater, "_http_get", release_get)
    monkeypatch.setattr(updater, "_plugin_dir", lambda: plugin_dir)
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    monkeypatch.setattr(updater, "read_version", cached_version)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(updater.install)
        assert download_started.wait(timeout=1)
        second = pool.submit(updater.install)
        time.sleep(0.05)
        assert downloads == 1
        release_download.set()
        first_result = first.result(timeout=1)
        second_result = second.result(timeout=1)

    assert first_result["ok"] is True
    assert second_result == {
        "ok": False,
        "needs_restart": False,
        "message": "no_asset",
    }
    assert downloads == 1


def test_check_does_not_install_an_older_release_when_latest_has_no_asset(updater, monkeypatch):
    monkeypatch.setattr(updater, "read_version", lambda: "0.1.0")
    monkeypatch.setattr(updater, "_repo_slug", lambda: "panel-de-control")
    monkeypatch.setattr(updater, "_plugin_name", lambda: "Panel de Control")
    latest = _release("0.3.0", "Latest")
    requested = []

    def release_get(url, accept):
        requested.append(url)
        if url.endswith("/latest"):
            return json.dumps(latest).encode()
        return json.dumps(
            [_release("0.2.0", "Older", asset_url="https://gh/older.zip")]
        ).encode()

    monkeypatch.setattr(updater, "_http_get", release_get)

    result = updater.check(force=True)

    assert requested == [
        "https://api.github.com/repos/Hooandee/panel-de-control/releases/latest",
    ]
    assert result["latest"] == "0.3.0"
    assert result["download_url"] == ""
    assert result["has_update"] is False


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


def test_extract_zip_preserves_executable_bit(updater, tmp_path):
    # zipfile.extractall() drops the unix mode the archive records, so a bundled
    # executable (bin/ryzenadj) lands non-executable and fails to run (EACCES).
    # _extract_zip must restore the recorded mode.
    import os
    import zipfile

    zpath = tmp_path / "release.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        exe = zipfile.ZipInfo("Plugin/bin/ryzenadj")
        exe.external_attr = 0o755 << 16
        zf.writestr(exe, b"\x7fELF binary")
        plain = zipfile.ZipInfo("Plugin/main.py")
        plain.external_attr = 0o644 << 16
        zf.writestr(plain, b"x = 1\n")

    dest = tmp_path / "out"
    with zipfile.ZipFile(zpath) as zf:
        updater._extract_zip(zf, dest)

    assert os.stat(dest / "Plugin/bin/ryzenadj").st_mode & 0o111 == 0o111
    assert os.stat(dest / "Plugin/main.py").st_mode & 0o111 == 0


def test_extract_zip_tolerates_missing_unix_mode(updater, tmp_path):
    # A zip made by a tool that records no unix mode (external_attr high bits == 0,
    # e.g. some Windows zippers) must still extract without error.
    import zipfile

    zpath = tmp_path / "nomodes.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("Plugin/main.py", b"x = 1\n")

    dest = tmp_path / "out"
    with zipfile.ZipFile(zpath) as zf:
        updater._extract_zip(zf, dest)
    assert (dest / "Plugin/main.py").read_text() == "x = 1\n"


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
