"""Armada OS integration points shared by power and fan control."""

import os

POWERD_UNIT = "armada-powerd.service"
_UNIT_PATHS = ("usr/lib/systemd/system", "etc/systemd/system")
_BUSCTL = ("/usr/bin/busctl", "/bin/busctl")


def powerd_present(root: str = "/") -> bool:
    return any(os.path.exists(os.path.join(root, base, POWERD_UNIT)) for base in _UNIT_PATHS)


def reload_powerd() -> bool:
    """Ask armada-powerd to re-apply its active profile. False when it is not running."""
    try:
        import subprocess
        from controllers.detect import clean_env
        busctl = next((path for path in _BUSCTL if os.path.exists(path)), "busctl")
        result = subprocess.run(
            [busctl, "--system", "call", "org.armada.Power", "/org/armada/Power",
             "org.armada.Power1", "Reload"],
            check=False, capture_output=True, timeout=5, env=clean_env(),
        )
        return result.returncode == 0
    except Exception:  # noqa: BLE001
        return False
