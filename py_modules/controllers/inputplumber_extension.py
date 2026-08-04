import hashlib
import os
import shutil
import subprocess
import re
import time

from controllers.detect import clean_env


VERSION = "0.77.4"
DEVICE_KEY = "rog_xbox_ally_x"
STOCK_SHA256 = "4781afc2e9d212419fc968cdd09a51bf804eee30e0932f2f847ace340a83c136"
STOCK_PATH = "/usr/bin/inputplumber"
SYSTEMCTL = "/usr/bin/systemctl"
BUSCTL = "/usr/bin/busctl"
SERVICE = "org.shadowblip.InputPlumber"
FF_IFACE = "org.shadowblip.Output.ForceFeedback"
INSTALL_DIR = f"/var/lib/panel-de-control/inputplumber/{VERSION}"
INSTALL_PATH = f"{INSTALL_DIR}/inputplumber"
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


def _cleanup_install():
    ok = True
    for path in (INSTALL_PATH, f"{INSTALL_PATH}.new"):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError:
            ok = False
    try:
        os.rmdir(INSTALL_DIR)
    except FileNotFoundError:
        pass
    except OSError:
        ok = False
    return ok


def _remove_override(run):
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
    return _cleanup_install()


def _unavailable(reason, run):
    changed = False
    if os.path.exists(DROPIN_PATH):
        changed = _remove_override(run)
    else:
        _cleanup_install()
    return {"available": False, "changed": changed, "reason": reason}


def ensure(device_key, plugin_dir, run=_run):
    if device_key != DEVICE_KEY:
        return _unavailable("wrong_device", run)
    bundled = os.path.join(
        plugin_dir, "bin", f"inputplumber-xbox-hd-v{VERSION}"
    )
    expected_path = f"{bundled}.sha256"
    try:
        with open(expected_path) as stream:
            expected = stream.read().strip()
    except OSError:
        return _unavailable("not_bundled", run)
    if _sha256(bundled) != expected:
        return _unavailable("bundle_mismatch", run)
    version = run([STOCK_PATH, "--version"])
    if not _ok(version) or version.stdout.strip() != f"inputplumber {VERSION}":
        return _unavailable("version_mismatch", run)
    if _sha256(STOCK_PATH) != STOCK_SHA256:
        return _unavailable("stock_mismatch", run)
    desired_dropin = (
        "[Service]\nExecStart=\n"
        f"ExecStart={INSTALL_PATH}\n"
    )
    try:
        installed = _sha256(INSTALL_PATH) == expected
        if os.path.exists(DROPIN_PATH):
            with open(DROPIN_PATH) as stream:
                current_dropin = stream.read()
        else:
            current_dropin = ""
        if installed and current_dropin == desired_dropin:
            if _wait_extension_healthy(run):
                return {"available": True, "changed": False, "reason": None}
            _remove_override(run)
            return {
                "available": False,
                "changed": False,
                "reason": "healthcheck_failed",
            }
        os.makedirs(INSTALL_DIR, mode=0o755, exist_ok=True)
        os.makedirs(DROPIN_DIR, mode=0o755, exist_ok=True)
        staged = f"{INSTALL_PATH}.new"
        shutil.copyfile(bundled, staged)
        os.chmod(staged, 0o755)
        os.replace(staged, INSTALL_PATH)
        dropin_staged = f"{DROPIN_PATH}.new"
        with open(dropin_staged, "w") as stream:
            stream.write(desired_dropin)
        os.replace(dropin_staged, DROPIN_PATH)
    except OSError:
        return _unavailable("install_failed", run)
    if _restart(run, require_extension=True):
        return {"available": True, "changed": True, "reason": None}
    _remove_override(run)
    return {"available": False, "changed": False, "reason": "healthcheck_failed"}


def uninstall(device_key, run=_run):
    if os.path.exists(DROPIN_PATH):
        return _remove_override(run)
    return _cleanup_install()
