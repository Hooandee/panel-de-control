"""Armada OS fan handoff: ``armada-powerd`` drives the pwm-fan every 3 s, so a Panel
curve only holds while that daemon is stopped. Stopping it is guarded by a transient
systemd unit that restarts the daemon if the Panel process disappears, because pwm-fan
has no firmware fallback: a dead loop would leave the fan at its last duty."""

import configparser
import os

from armada_os import POWERD_UNIT, powerd_present
from fans.generic_pwm import GenericPwmFanBackend
from fans.software_loop import _systemctl_path

__all__ = ["ArmadaFanBackend", "SystemdPowerdControl", "powerd_min_duty", "powerd_present"]

GUARD_UNIT = "pdc-armada-fan-guard"
_CONFIGS = ("etc/armada/power-profiles.conf", "usr/share/armada/power-profiles.conf")
_DEFAULT_MIN_DUTY = 51


def powerd_min_duty(root: str = "/") -> int:
    for rel in _CONFIGS:
        parser = configparser.ConfigParser()
        try:
            if parser.read(os.path.join(root, rel)) and parser.has_option("fan", "min_pwm"):
                return max(0, min(255, parser.getint("fan", "min_pwm")))
        except (configparser.Error, ValueError):
            continue
    return _DEFAULT_MIN_DUTY


def _run(argv: list[str]) -> bool:
    try:
        import subprocess
        from controllers.detect import clean_env
        result = subprocess.run(argv, check=False, capture_output=True, timeout=10, env=clean_env())
        return result.returncode == 0
    except Exception:  # noqa: BLE001
        return False


class SystemdPowerdControl:
    def __init__(self, pid: int | None = None) -> None:
        self._pid = pid if pid is not None else os.getpid()
        self._systemctl = _systemctl_path()

    def start_guard(self) -> bool:
        self.stop_guard()
        sc = self._systemctl
        watch = (
            f"while kill -0 {int(self._pid)} 2>/dev/null; do sleep 2; done; "
            f"{sc} unmask --runtime {POWERD_UNIT}; {sc} reset-failed {POWERD_UNIT}; "
            f"exec {sc} start {POWERD_UNIT}"
        )
        return _run([
            os.path.join(os.path.dirname(self._systemctl), "systemd-run"),
            f"--unit={GUARD_UNIT}", "--collect", "--quiet", "/bin/sh", "-c", watch,
        ])

    def stop_guard(self) -> bool:
        return _run([self._systemctl, "stop", GUARD_UNIT])

    def stop_powerd(self) -> bool:
        # A runtime mask also blocks the boot-time start that can land after Panel
        # loads; /run is cleared on reboot, so a mask can never outlive the session.
        return _run([self._systemctl, "mask", "--runtime", "--now", POWERD_UNIT])

    def start_powerd(self) -> bool:
        _run([self._systemctl, "unmask", "--runtime", POWERD_UNIT])
        _run([self._systemctl, "reset-failed", POWERD_UNIT])
        return _run([self._systemctl, "start", POWERD_UNIT])


class ArmadaFanBackend(GenericPwmFanBackend):
    name = "armada-pwm"

    def __init__(self, temp_fn=None, root: str = "/", control=None) -> None:
        super().__init__(temp_fn=temp_fn, root=root, min_duty=powerd_min_duty(root))
        self._control = control if control is not None else SystemdPowerdControl()
        self._powerd_stopped = False

    def _before_drive(self) -> bool:
        if self._powerd_stopped:
            return True
        if not self._control.start_guard():
            return False
        if not self._control.stop_powerd():
            self._control.stop_guard()
            return False
        self._powerd_stopped = True
        return super()._before_drive()

    def _after_release(self) -> bool:
        started = self._control.start_powerd()
        if started:
            self._control.stop_guard()
            self._powerd_stopped = False
        return started

    @property
    def _owns_fan(self) -> bool:
        return self._points is not None and self._powerd_stopped
