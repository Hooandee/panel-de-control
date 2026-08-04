"""Version-gated, reversible InputPlumber extension for Xbox Ally X haptics."""
import hashlib
import os
import shutil
import subprocess
import time

from controllers.detect import clean_env


VERSION = "0.77.4"
DEVICE_KEY = "rog_xbox_ally_x"
STOCK_SHA256 = "4781afc2e9d212419fc968cdd09a51bf804eee30e0932f2f847ace340a83c136"
STOCK_PATH = "/usr/bin/inputplumber"
SYSTEMCTL = "/usr/bin/systemctl"
INSTALL_DIR = f"/var/lib/panel-de-control/inputplumber/{VERSION}"
INSTALL_PATH = f"{INSTALL_DIR}/inputplumber"
DROPIN_DIR = "/etc/systemd/system/inputplumber.service.d"
DROPIN_PATH = f"{DROPIN_DIR}/90-panel-hd-haptics.conf"


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


def _restart(run):
    if not _ok(run([SYSTEMCTL, "daemon-reload"])):
        return False
    if not _ok(run([SYSTEMCTL, "restart", "inputplumber"])):
        return False
    for _attempt in range(12):
        if _ok(run([SYSTEMCTL, "is-active", "inputplumber"])):
            return True
        time.sleep(0.25)
    return False


def _remove_override(run):
    try:
        os.unlink(DROPIN_PATH)
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return _restart(run)


def ensure(device_key, plugin_dir, run=_run):
    if device_key != DEVICE_KEY:
        return {"available": False, "changed": False, "reason": "wrong_device"}
    bundled = os.path.join(
        plugin_dir, "bin", f"inputplumber-xbox-hd-v{VERSION}"
    )
    expected_path = f"{bundled}.sha256"
    try:
        with open(expected_path) as stream:
            expected = stream.read().strip()
    except OSError:
        return {"available": False, "changed": False, "reason": "not_bundled"}
    if _sha256(bundled) != expected:
        return {"available": False, "changed": False, "reason": "bundle_mismatch"}
    version = run([STOCK_PATH, "--version"])
    if not _ok(version) or version.stdout.strip() != f"inputplumber {VERSION}":
        return {"available": False, "changed": False, "reason": "version_mismatch"}
    if _sha256(STOCK_PATH) != STOCK_SHA256:
        return {"available": False, "changed": False, "reason": "stock_mismatch"}
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
            return {"available": True, "changed": False, "reason": None}
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
        return {"available": False, "changed": False, "reason": "install_failed"}
    if _restart(run):
        return {"available": True, "changed": True, "reason": None}
    _remove_override(run)
    return {"available": False, "changed": False, "reason": "healthcheck_failed"}


def uninstall(device_key, run=_run):
    if device_key != DEVICE_KEY or not os.path.exists(DROPIN_PATH):
        return True
    return _remove_override(run)
