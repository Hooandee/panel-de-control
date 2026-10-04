"""Armada OS fan handoff: ``armada-powerd`` drives the pwm-fan every 3 s, so a Panel
curve only holds while that daemon is stopped. Stopping it is guarded by a transient
systemd unit that restarts the daemon as soon as Panel's fan loop stops beating,
because pwm-fan has no firmware fallback: a dead loop would leave the fan at its last
duty."""

import configparser
import os
import time

from armada_os import POWERD_UNIT, powerd_present
from fans.generic_pwm import GenericPwmFanBackend
from fans.software_loop import _systemctl_path

__all__ = ["ArmadaFanBackend", "SystemdPowerdControl", "powerd_min_duty", "powerd_present"]

GUARD_PREFIX = "pdc-armada-fan-guard"
HEARTBEAT = "/run/pdc-armada-fan.alive"
_HEARTBEAT_STALE_S = 15
_VERIFY_INTERVAL_S = 10.0
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


def _run(argv: list[str]) -> tuple[bool, str]:
    try:
        import subprocess
        from controllers.detect import clean_env
        result = subprocess.run(argv, check=False, capture_output=True, text=True,
                                timeout=10, env=clean_env())
        return result.returncode == 0, (result.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return False, ""


class SystemdPowerdControl:
    def __init__(self, pid: int | None = None, heartbeat: str = HEARTBEAT) -> None:
        self._pid = pid if pid is not None else os.getpid()
        self._heartbeat = heartbeat
        self._guard = f"{GUARD_PREFIX}-{self._pid}"
        self._systemctl = _systemctl_path()

    def beat(self) -> None:
        try:
            with open(self._heartbeat, "w") as handle:
                handle.write(str(self._pid))
        except OSError:
            pass

    def start_guard(self) -> bool:
        sc = self._systemctl
        self.beat()
        watch = (
            f"while kill -0 {int(self._pid)} 2>/dev/null"
            f" && [ $(( $(date +%s) - $(stat -c %Y {self._heartbeat} 2>/dev/null || echo 0) ))"
            f" -lt {_HEARTBEAT_STALE_S} ]; do sleep 2; done; "
            f"{sc} unmask --runtime {POWERD_UNIT}; {sc} reset-failed {POWERD_UNIT}; "
            f"exec {sc} start {POWERD_UNIT}"
        )
        if self.guard_active():
            return True
        return _run([
            os.path.join(os.path.dirname(sc), "systemd-run"),
            f"--unit={self._guard}", "--collect", "--quiet", "/bin/sh", "-c", watch,
        ])[0]

    def guard_active(self) -> bool:
        return _run([self._systemctl, "is-active", self._guard])[1] == "active"

    def stop_guard(self) -> bool:
        return _run([self._systemctl, "stop", self._guard])[0]

    def powerd_active(self) -> bool:
        return _run([self._systemctl, "is-active", POWERD_UNIT])[1] == "active"

    def stop_powerd(self) -> bool:
        # A runtime mask also blocks the boot-time start that can land after Panel
        # loads; /run is cleared on reboot, so a mask can never outlive the session.
        _run([self._systemctl, "mask", "--runtime", "--now", POWERD_UNIT])
        return not self.powerd_active()

    def start_powerd(self) -> bool:
        _run([self._systemctl, "unmask", "--runtime", POWERD_UNIT])
        _run([self._systemctl, "reset-failed", POWERD_UNIT])
        _run([self._systemctl, "start", POWERD_UNIT])
        return self.powerd_active()


class ArmadaFanBackend(GenericPwmFanBackend):
    name = "armada-pwm"

    def __init__(self, temp_fn=None, root: str = "/", control=None, clock=time.monotonic) -> None:
        super().__init__(temp_fn=temp_fn, root=root, min_duty=powerd_min_duty(root))
        self._control = control if control is not None else SystemdPowerdControl()
        self._clock = clock
        self._powerd_stopped = False
        self._verified_at = float("-inf")

    def _has_firmware_auto(self) -> bool:
        return True

    def _take(self) -> bool:
        if not self._control.start_guard():
            return False
        if not self._control.stop_powerd():
            self._hand_back()
            return False
        self._powerd_stopped = True
        self._verified_at = self._clock()
        return True

    def _hand_back(self) -> bool:
        started = self._control.start_powerd()
        if started:
            self._control.stop_guard()
            self._powerd_stopped = False
        return started

    def _before_drive(self) -> bool:
        if not self._powerd_stopped and not self._take():
            return False
        return super()._before_drive()

    def _apply_once_locked(self) -> bool:
        if self._points is not None:
            now = self._clock()
            if self._powerd_stopped and now - self._verified_at >= _VERIFY_INTERVAL_S:
                self._verified_at = now
                if self._control.powerd_active():
                    self._powerd_stopped = False
            if not self._powerd_stopped and not self._take():
                self._drive_ok = False
                return False
            self._control.beat()
        return super()._apply_once_locked()

    def _release(self) -> bool:
        released = super()._release()
        handed_back = self._hand_back() if self._powerd_stopped else True
        return released and handed_back

    def _after_release(self) -> bool:
        return self._hand_back() if self._powerd_stopped else self._control.powerd_active()

    @property
    def _owns_fan(self) -> bool:
        return self._points is not None and self._powerd_stopped
