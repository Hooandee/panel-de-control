"""Expose the Legion Go S fan sensor.

On the Legion Go S the upstream ``lenovo_wmi_other`` driver hides its fan hwmon
node behind a capability check unless the module is loaded with
``expose_all_fans=Y``. We drop a modprobe.d option (so it survives reboots) and
reload the module live (its refcount is 0 → safe; the ``ppt_*`` firmware
attributes it also provides are re-created on load).

Root-only, idempotent, never raises. On any device that lacks the
``lenovo_wmi_other`` module parameter this is a no-op, so it is safe to call
unconditionally at plugin load.
"""

import glob
import os
import subprocess

_MODULE = "lenovo_wmi_other"
_PARAM = f"sys/module/{_MODULE}/parameters/expose_all_fans"
_HWMON = "sys/class/hwmon"
_MODPROBE_CONF = "etc/modprobe.d/panel-de-control-legion-fan.conf"
_CONF_BODY = (
    "# Panel de Control: expose the Legion Go S fan sensor (lenovo_wmi_other)\n"
    f"options {_MODULE} expose_all_fans=Y\n"
)


def _param_exists(root: str) -> bool:
    return os.path.exists(os.path.join(root, _PARAM))


def _fan_node_present(root: str) -> bool:
    for d in glob.glob(os.path.join(root, _HWMON, "hwmon*")):
        try:
            with open(os.path.join(d, "name")) as f:
                name = f.read().strip()
        except OSError:
            continue
        if name == _MODULE and glob.glob(os.path.join(d, "fan*_input")):
            return True
    return False


def _default_run(cmd: list) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=15).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def ensure_fan_sensor(*, run=_default_run, root: str = "/") -> bool:
    """Make the lenovo_wmi_other fan hwmon visible. Returns True if a fan node is
    present afterwards. No-op (returns False) on devices without the parameter."""
    try:
        if not _param_exists(root):
            return False  # not a lenovo_wmi_other device — nothing to expose
        if _fan_node_present(root):
            return True  # already exposed (e.g. modprobe.d applied at boot)

        # Persist for future boots (non-fatal if the FS is read-only).
        conf = os.path.join(root, _MODPROBE_CONF)
        try:
            existing = open(conf).read() if os.path.exists(conf) else ""
            if "expose_all_fans=Y" not in existing:
                os.makedirs(os.path.dirname(conf), exist_ok=True)
                with open(conf, "w") as f:
                    f.write(_CONF_BODY)
        except OSError:
            pass

        # Reload now so it works this session without a reboot. Pass the param
        # explicitly too (belt-and-suspenders if the conf write failed).
        run(["modprobe", "-r", _MODULE])
        run(["modprobe", _MODULE, "expose_all_fans=Y"])
        return _fan_node_present(root)
    except Exception:  # noqa: BLE001
        return False


def remove_conf(root: str = "/") -> None:
    """Drop the modprobe.d option (called on uninstall). Never raises."""
    try:
        os.remove(os.path.join(root, _MODPROBE_CONF))
    except OSError:
        pass
