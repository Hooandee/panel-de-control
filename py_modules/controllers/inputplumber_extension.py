import hashlib
import os
import shutil
import subprocess
import re
import time

from controllers.detect import clean_env
from controllers.inputplumber_compat import (
    DEVICE_KEY,
    MANAGER,
    ManifestError,
    load_builds,
    select_build,
)


STOCK_PATH = "/usr/bin/inputplumber"
SYSTEMCTL = "/usr/bin/systemctl"
BUSCTL = "/usr/bin/busctl"
SERVICE = "org.shadowblip.InputPlumber"
FF_IFACE = "org.shadowblip.Output.ForceFeedback"
INSTALL_ROOT = "/var/lib/panel-de-control/inputplumber"
DROPIN_DIR = "/etc/systemd/system/inputplumber.service.d"
DROPIN_PATH = f"{DROPIN_DIR}/90-panel-hd-haptics.conf"
HEALTHCHECK_ATTEMPTS = 20
HEALTHCHECK_INTERVAL = 0.25


def _run(args):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=15, check=False,
            env=clean_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _sha256(path):
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _ok(result):
    return result is not None and result.returncode == 0


def _extension_healthy(run):
    tree = run([BUSCTL, "tree", SERVICE])
    if not _ok(tree):
        return False
    paths = re.findall(
        r"(/org/shadowblip/InputPlumber/CompositeDevice\d+)",
        tree.stdout,
    )
    return any(
        _ok(result := run([
            BUSCTL, "get-property", SERVICE, path, FF_IFACE,
            "XboxHdHapticsSupported",
        ]))
        and re.search(r"\btrue\b", result.stdout)
        for path in paths
    )


def _wait_extension_healthy(run):
    for attempt in range(HEALTHCHECK_ATTEMPTS):
        if _extension_healthy(run):
            return True
        if attempt + 1 < HEALTHCHECK_ATTEMPTS:
            time.sleep(HEALTHCHECK_INTERVAL)
    return False


def _restart(run, require_extension=False):
    if not _ok(run([SYSTEMCTL, "daemon-reload"])):
        return False
    if not _ok(run([SYSTEMCTL, "restart", "inputplumber"])):
        return False
    if not _ok(run([SYSTEMCTL, "is-active", "inputplumber"])):
        return False
    return not require_extension or _wait_extension_healthy(run)


def _build_install_path(version):
    return os.path.join(INSTALL_ROOT, version, "inputplumber")


def _cleanup_install(install_paths=()):
    ok = True
    for install_path in install_paths:
        for path in (install_path, f"{install_path}.new"):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            except OSError:
                ok = False
        try:
            os.rmdir(os.path.dirname(install_path))
        except FileNotFoundError:
            pass
        except OSError:
            ok = False
    return ok


def _remove_override(run, install_paths=()):
    previous = None
    try:
        with open(DROPIN_PATH) as stream:
            previous = stream.read()
    except OSError:
        pass
    try:
        os.unlink(DROPIN_PATH)
    except FileNotFoundError:
        pass
    except OSError:
        return False
    if not _restart(run):
        if previous is not None:
            try:
                with open(DROPIN_PATH, "w") as stream:
                    stream.write(previous)
            except OSError:
                return False
        _restart(run, require_extension=previous is not None)
        return False
    return _cleanup_install(install_paths)


def _unavailable(reason, run, install_paths=()):
    existing_install = any(
        os.path.exists(path) or os.path.exists(f"{path}.new")
        for path in install_paths
    )
    if os.path.exists(DROPIN_PATH):
        changed = _remove_override(run, install_paths)
    else:
        changed = existing_install and _cleanup_install(install_paths)
    return {"available": False, "changed": changed, "reason": reason}


def ensure(device_key, manager, plugin_dir, run=_run):
    if manager != MANAGER:
        return {
            "available": False,
            "changed": False,
            "reason": "wrong_manager",
        }
    if device_key != DEVICE_KEY:
        return {
            "available": False,
            "changed": False,
            "reason": "wrong_device",
        }
    try:
        builds = load_builds(plugin_dir)
    except ManifestError:
        return _unavailable("manifest_invalid", run)
    install_paths = tuple(
        _build_install_path(build.version) for build in builds
    )
    version_result = run([STOCK_PATH, "--version"])
    if not _ok(version_result):
        return _unavailable("stock_unavailable", run, install_paths)
    match = re.fullmatch(
        r"inputplumber ([0-9]+\.[0-9]+\.[0-9]+)",
        version_result.stdout.strip(),
    )
    if match is None:
        return _unavailable("version_invalid", run, install_paths)
    version = match.group(1)
    version_builds = tuple(
        build for build in builds if build.version == version
    )
    if not version_builds:
        return _unavailable("unsupported_version", run, install_paths)
    stock_hash = _sha256(STOCK_PATH)
    build = select_build(
        builds,
        manager=manager,
        device_key=device_key,
        version=version,
        stock_sha256=stock_hash,
    )
    if build is None:
        return _unavailable("stock_mismatch", run, install_paths)
    bundled = os.path.join(plugin_dir, build.artifact)
    expected_path = os.path.join(plugin_dir, build.artifact_sha256)
    try:
        with open(expected_path) as stream:
            expected = stream.read().strip()
    except OSError:
        return _unavailable("not_bundled", run, install_paths)
    if _sha256(bundled) != expected:
        return _unavailable("bundle_mismatch", run, install_paths)
    install_path = _build_install_path(build.version)
    install_dir = os.path.dirname(install_path)
    desired_dropin = (
        "[Service]\nExecStart=\n"
        f"ExecStart={install_path}\n"
    )
    try:
        installed = _sha256(install_path) == expected
        if os.path.exists(DROPIN_PATH):
            with open(DROPIN_PATH) as stream:
                current_dropin = stream.read()
        else:
            current_dropin = ""
        if installed and current_dropin == desired_dropin:
            if _wait_extension_healthy(run):
                return {
                    "available": True,
                    "changed": False,
                    "reason": None,
                    "version": build.version,
                }
            _remove_override(run, install_paths)
            return {
                "available": False,
                "changed": False,
                "reason": "healthcheck_failed",
            }
        os.makedirs(install_dir, mode=0o755, exist_ok=True)
        os.makedirs(DROPIN_DIR, mode=0o755, exist_ok=True)
        staged = f"{install_path}.new"
        shutil.copyfile(bundled, staged)
        os.chmod(staged, 0o755)
        os.replace(staged, install_path)
        dropin_staged = f"{DROPIN_PATH}.new"
        with open(dropin_staged, "w") as stream:
            stream.write(desired_dropin)
        os.replace(dropin_staged, DROPIN_PATH)
    except OSError:
        return _unavailable("install_failed", run, install_paths)
    if _restart(run, require_extension=True):
        return {
            "available": True,
            "changed": True,
            "reason": None,
            "version": build.version,
        }
    _remove_override(run, install_paths)
    return {"available": False, "changed": False, "reason": "healthcheck_failed"}


def uninstall(device_key, plugin_dir, run=_run):
    try:
        builds = load_builds(plugin_dir)
    except ManifestError:
        builds = ()
    install_paths = tuple(
        _build_install_path(build.version) for build in builds
    )
    if os.path.exists(DROPIN_PATH):
        return _remove_override(run, install_paths)
    return _cleanup_install(install_paths)
