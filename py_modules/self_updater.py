"""Self-updater: check GitHub releases and install the latest zip in place.

Distributed outside the Decky store, so this lets users update from within the plugin.
Every public function NEVER raises — it returns a status dict so the UI renders a message
instead of hanging on a spinner.

Repo-specific values are read at runtime, so this file is identical across plugins:
  - repo slug  = package.json "name"   (matches the GitHub repo, e.g. "decky-colores")
  - zip / dir  = plugin.json "name"    (release asset base name & installed dir name)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import decky

from http_util import ssl_context  # top-level import (Decky adds py_modules to sys.path)
from version import read_version

_GITHUB_OWNER = "Hooandee"
_UA = "decky-self-updater"

# Session cache: only hit GitHub once per Steam session (force=True bypasses it).
_cache: dict | None = None
_operation_lock = threading.RLock()


def _plugin_dir() -> Path:
    # Same derivation as version.py: py_modules/ -> plugin root.
    return Path(__file__).resolve().parent.parent


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _repo_slug() -> str:
    return str(_read_json(_plugin_dir() / "package.json").get("name", ""))


def _plugin_name() -> str:
    return str(_read_json(_plugin_dir() / "plugin.json").get("name", ""))


_SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _extract_semver(tag: str) -> str:
    """Pull the X.Y.Z out of a release-please tag.

    release-please tags are '<package>-v<semver>' (e.g. 'decky-colores-v0.14.0'),
    and can also be plain 'v0.14.0' — so match the semver anywhere in the tag.
    """
    m = _SEMVER.search(tag or "")
    return m.group(0) if m else ""


def _norm(v: str) -> tuple[int, int, int]:
    m = _SEMVER.search(v or "")
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _is_newer(latest: str, current: str) -> bool:
    return _norm(latest) > _norm(current)


def _http_get(url: str, accept: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=15, context=ssl_context()) as resp:  # noqa: S310
        return resp.read()


def _shape(data: dict, current: str) -> dict:
    """Turn a GitHub 'releases/latest' payload into the UpdateInfo dict."""
    latest = _extract_semver(str(data.get("tag_name", "")))
    notes = str(data.get("body", "") or "")
    zip_name = f"{_plugin_name()}.zip"
    # GitHub replaces spaces with dots in release asset names, so
    # "Panel de Control.zip" is stored as "Panel.de.Control.zip".
    candidates = {zip_name, zip_name.replace(" ", ".")}
    download_url = ""
    for asset in data.get("assets", []) or []:
        if asset.get("name") in candidates:
            download_url = str(asset.get("browser_download_url", ""))
            break
    return {
        "current": current,
        "latest": latest or current,
        "notes": notes,
        "download_url": download_url,
        "has_update": bool(latest) and bool(download_url) and _is_newer(latest, current),
        "error": "",
    }


def _release_notes(data: list[dict], current: str, latest: str) -> str:
    releases: dict[str, dict] = {}
    for release in data:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        version = _extract_semver(str(release.get("tag_name", "")))
        if (
            version
            and _is_newer(version, current)
            and not _is_newer(version, latest)
        ):
            releases.setdefault(version, release)

    notes: list[str] = []
    for version in sorted(releases, key=_norm, reverse=True):
        release = releases[version]
        body = str(release.get("body", "") or "").strip()
        notes.append(f"## v{version}" + (f"\n\n{body}" if body else ""))
    return "\n\n".join(notes)


def _fetch_releases(slug: str) -> list[dict]:
    releases: list[dict] = []
    page = 1
    while True:
        api = (
            f"https://api.github.com/repos/{_GITHUB_OWNER}/{slug}/releases"
            f"?per_page=100&page={page}"
        )
        batch = json.loads(_http_get(api, "application/vnd.github+json"))
        if not isinstance(batch, list):
            raise ValueError("unexpected releases response")
        releases.extend(batch)
        if len(batch) < 100:
            return releases
        page += 1


def check(force: bool = False) -> dict:
    global _cache
    with _operation_lock:
        if _cache is not None and not force:
            return _cache
        current = read_version()
        empty = {
            "current": current,
            "latest": current,
            "has_update": False,
            "notes": "",
            "download_url": "",
            "error": "",
        }
        result = empty
        latest_loaded = False
        try:
            slug = _repo_slug()
            latest_api = f"https://api.github.com/repos/{_GITHUB_OWNER}/{slug}/releases/latest"
            latest_data = json.loads(_http_get(latest_api, "application/vnd.github+json"))
            latest_loaded = True
            result = _shape(latest_data, current)
            if result["has_update"]:
                releases = [latest_data, *_fetch_releases(slug)]
                result["notes"] = _release_notes(
                    releases, current, result["latest"]
                )
        except urllib.error.HTTPError as e:
            if e.code == 404 and not latest_loaded:
                decky.logger.info("[updater] no published release yet")
            else:
                decky.logger.warning(f"[updater] check failed: {e}")
                result = {**empty, "error": "network"}
        except Exception as e:  # noqa: BLE001 — must never propagate to the UI
            decky.logger.warning(f"[updater] check failed: {e}")
            result = {**empty, "error": "network"}
        _cache = result
        return result


def _extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract preserving the unix permission bits the archive records. plain
    extractall() drops them, so a bundled executable (bin/ryzenadj) would land
    non-executable and fail to run. A zip with no recorded mode (external_attr high
    bits == 0) keeps the default extract."""
    for info in zf.infolist():
        out = zf.extract(info, dest)
        # Low 9 bits only (rwx for u/g/o); never carry setuid/setgid/sticky from a zip.
        mode = (info.external_attr >> 16) & 0o777
        if mode:
            os.chmod(out, mode)


def install() -> dict:
    """Download the latest release zip and overwrite the installed plugin dir in place.

    Returns {ok, needs_restart, message}. Never raises.
    """
    with _operation_lock:
        info = check()
        url = str(info.get("download_url") or "")
        if not info.get("has_update") or not url:
            return {"ok": False, "needs_restart": False, "message": "no_asset"}
        try:
            plugin_dir = _plugin_dir()
            name = _plugin_name()
            blob = _http_get(url, "application/octet-stream")
            with tempfile.TemporaryDirectory() as tmp:
                tmpd = Path(tmp)
                zpath = tmpd / "update.zip"
                zpath.write_bytes(blob)
                extract = tmpd / "x"
                with zipfile.ZipFile(zpath) as zf:
                    _extract_zip(zf, extract)
                src = extract / name  # top folder == plugin.json name
                if not src.is_dir():
                    subdirs = [p for p in extract.iterdir() if p.is_dir()]
                    if len(subdirs) == 1:
                        src = subdirs[0]
                if not src.is_dir():
                    return {"ok": False, "needs_restart": False, "message": "bad_zip"}
                # Copy over the installed plugin dir. User settings live in
                # DECKY_PLUGIN_SETTINGS_DIR (outside this dir) and are untouched.
                for item in src.iterdir():
                    dest = plugin_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest)
            read_version.cache_clear()
            _mark_installed()
            return {"ok": True, "needs_restart": True, "message": "installed"}
        except Exception as e:  # noqa: BLE001
            decky.logger.error(f"[updater] install failed: {e}")
            return {"ok": False, "needs_restart": False, "message": "install_failed"}


def restart_loader() -> None:
    """Restart Decky to load the just-installed files. Fire-and-forget (kills this process)."""
    try:
        import subprocess

        # Decky's PyInstaller build points LD_LIBRARY_PATH at its bundled libs
        # (an older libcrypto), which makes system binaries like systemctl fail
        # with "OPENSSL_x not found". Restore the pre-bundle library path (or drop
        # it) so systemctl loads the system libraries.
        env = dict(os.environ)
        orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if orig is not None:
            env["LD_LIBRARY_PATH"] = orig
        else:
            env.pop("LD_LIBRARY_PATH", None)
        subprocess.Popen(["/usr/bin/systemctl", "restart", "plugin_loader"], env=env)  # noqa: S603
    except Exception as e:  # noqa: BLE001
        decky.logger.error(f"[updater] restart failed: {e}")


def _mark_installed() -> None:
    global _cache
    if _cache:
        _cache = {**_cache, "current": _cache.get("latest", _cache.get("current")), "has_update": False}
