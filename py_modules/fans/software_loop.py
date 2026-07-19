"""Software-loop fan backends — for devices with NO hardware temp→pwm curve
table. We are the controller: read temp, interpolate the (canonical 0–255 pwm)
curve to a duty, map duty → an RPM target, write it, and re-assert periodically
(the EC reclaims the fan otherwise). Release = hand control back to firmware.

Members: Steam Deck (steamdeck_hwmon `fan1_target` RPM). Legion Go 2 (raw EC)
is a separate W4 backend with the same shape.

Canonical curve stays temp→pwm(0–255); each backend reinterprets pwm/255 as a
fraction of its RPM range so the curve representation is portable.
"""

import asyncio
import glob
import os
import threading
from typing import Callable, Optional

# Reuse the sysfs read/write + interp helpers from control (no 4th copy).
from fans.control import _interp, _read, _read_int, _write, sanitize_curve

_HWMON = "sys/class/hwmon"
_LOOP_INTERVAL = 1.5  # s — re-assert cadence (EC can reclaim the fan)

# RPM tolerance for deciding whether the fan obeyed an asserted target.
_DRIVE_CONFIRM_TOL_RPM = 500


def drive_confirmed(target, rpm, tol=_DRIVE_CONFIRM_TOL_RPM):
    """True if RPM is within `tol` of an asserted positive target, False if it's
    well off, None when indeterminate (no target / release / no reading)."""
    if target is None or target <= 0 or rpm is None:
        return None
    return abs(rpm - target) <= tol


class SoftwareLoopBackend:
    """Base: owns the stored curve, the asyncio re-assert loop, and duty→RPM."""

    name = "software-loop"
    # Drives a periodic re-assert loop that can wedge (EC reclaims the fan, a write
    # path closes) → the UI offers a reset. Hardware-curve backends can't wedge.
    resettable = True
    min_rpm = 0
    max_rpm = 7000
    # While a curve is ACTIVE the driven target must never be 0 — on these devices
    # writing 0 to the target/override is the "release to firmware" sentinel
    # (see _release). A 0%-duty cool point would otherwise silently hand the fan
    # back to the EC while read_state still reports manual. Clamp to >=1 so driving
    # stays manual (matches LeGo2's 0→1 behaviour); explicit release still writes 0.
    min_drive_rpm = 1

    def __init__(self, temp_fn: Optional[Callable[[], Optional[float]]] = None, root: str = "/") -> None:
        self._temp_fn = temp_fn
        self._root = root
        self._points: Optional[list] = None
        # Confirmed against the tachometer each tick: manual only when the RPM tracked
        # the target we asserted (a write can succeed yet be ignored by the firmware).
        self._drive_ok: bool = False
        self._prev_target: Optional[int] = None
        self._task: Optional[asyncio.Task] = None
        # The loop the task runs on, captured on start() (loop thread). stop() runs
        # from a worker thread (set_auto off-loop), so it must cancel via this loop.
        self._loop_ref: Optional[asyncio.AbstractEventLoop] = None
        # Serialises a per-tick write against a release: the tick now runs off-loop
        # (asyncio.to_thread), so without this a release write could interleave with
        # an in-flight tick and leave a stale target after we hand the fan back.
        self._io_lock = threading.Lock()
        self._dir: Optional[str] = self._find_chip()

    # --- subclass hooks --------------------------------------------------------
    def _find_chip(self) -> Optional[str]:
        raise NotImplementedError

    def _write_target(self, rpm: int) -> bool:
        raise NotImplementedError

    def _release(self) -> bool:
        raise NotImplementedError

    def _read_rpm(self) -> Optional[int]:
        return None

    def _before_drive(self) -> bool:
        """Take ownership of the fan before writing a target. Return True if we
        now own it. Override on devices where a firmware/OS daemon must be
        stopped first (Steam Deck's jupiter-fan-control). Default: always ok."""
        return True

    def _after_release(self) -> bool:
        """Hand ownership back after releasing the fan (fail-safe). Override to
        restart a stopped daemon; return whether the daemon is now running (so a
        failed handback is reflected in ok). Default: nothing to restart → True."""
        return True

    @property
    def _owns_fan(self) -> bool:
        """True only when we actually drive the fan (points set AND ownership
        acquired). read_state reports manual only when this AND `_drive_ok` hold."""
        return self._points is not None

    # --- common API ------------------------------------------------------------
    @property
    def supported(self) -> bool:
        return self._dir is not None

    def _duty_to_target(self, duty: int) -> int:
        frac = max(0, min(255, duty)) / 255
        return int(round(self.min_rpm + frac * (self.max_rpm - self.min_rpm)))

    def target_for_temp(self, temp: Optional[float]) -> Optional[int]:
        if self._points is None or temp is None:
            return None
        # Clamp to min_drive_rpm so an active curve never writes the release sentinel.
        return max(self.min_drive_rpm, self._duty_to_target(_interp(self._points, temp)))

    def read_state(self) -> dict:
        if not self.supported:
            return {"supported": False, "source": self.name, "pwm_max": 255, "fans": []}
        rpm = self._read_rpm()
        # Manual only when we own the fan AND the last asserted target tracked.
        manual = self._owns_fan and self._drive_ok
        return {"supported": True, "source": self.name, "pwm_max": 255,
                "fans": [{"key": "fan", "enable": 1 if manual else 2,
                          "rpm": rpm, "points": []}]}

    def apply_curve_all(self, points: list) -> dict:
        if not self.supported:
            return {"ok": False, "detail": f"{self.name} not found"}
        # Whole ownership transition under the lock so a concurrent set_auto() can't
        # interleave (release the fan / restart the daemon) mid-apply.
        with self._io_lock:
            # Take ownership of the fan FIRST. If we can't (e.g. jupiter-fan-control
            # refused to stop), we do NOT own the fan → never claim to drive and
            # never write a target the OS daemon would fight.
            if not self._before_drive():
                return {"ok": False, "detail": f"{self.name} could not take fan control"}
            self._points = [list(p) for p in sanitize_curve(points)]
            ok = self._apply_once_locked()  # immediate response, before the loop's first tick
        # Start the loop even if this write was refused, so control resumes if the
        # write path reopens; read_state still reports the true drive state.
        self.start()
        if ok:
            return {"ok": True, "detail": f"{self.name} curve applied (software loop)"}
        return {"ok": False, "detail": f"{self.name} target write refused"}

    def set_curve(self, fan_key, points: list) -> dict:
        return self.apply_curve_all(points)

    def set_auto(self, fan_key: Optional[str] = None) -> dict:
        if not self.supported:
            return {"ok": False, "detail": f"{self.name} not found"}
        # Stop the periodic loop (cancels the task; a tick already mid-write holds
        # the io lock and finishes first).
        self.stop()
        # Clear + release + handback under the lock, mutually exclusive with
        # apply_curve_all so the two can never leave a torn state.
        with self._io_lock:
            self._points = None
            self._drive_ok = False
            self._prev_target = None
            released = self._release()
            # Hand back to the daemon LAST (fail-safe): even a failed release must
            # never leave the loop dead AND the daemon stopped. Its result counts
            # toward ok — a fan whose OS daemon didn't restart isn't back to firmware.
            handed_back = self._after_release()
        ok = bool(released and handed_back)
        detail = ("released to firmware" if ok
                  else "release write failed" if not released
                  else "firmware handback failed")
        return {"ok": ok, "detail": detail}

    def restore_auto(self) -> dict:
        return self.set_auto(None)

    # --- the loop --------------------------------------------------------------
    def _apply_once(self) -> bool:
        """Write the current target once, holding the io lock so a release can't
        interleave. The loop path enters here; the apply/set_auto paths already hold
        the lock and call `_apply_once_locked` directly."""
        with self._io_lock:
            return self._apply_once_locked()

    def _apply_once_locked(self) -> bool:
        """Write the current target once (caller holds `_io_lock`). Before writing,
        confirm last tick's target against the live RPM to set `_drive_ok`. Returns
        whether the write landed; a None target (not driving / no temp) writes
        nothing."""
        temp = self._temp_fn() if self._temp_fn else None
        target = self.target_for_temp(temp)
        if target is None:
            return False
        if target <= 0:
            self._drive_ok = False  # the curve hands the fan to firmware here (not driving)
        else:
            verdict = drive_confirmed(self._prev_target, self._read_rpm())
            if verdict is not None:
                self._drive_ok = verdict
        wrote = self._write_target(target)
        self._prev_target = target
        return wrote

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no event loop (tests / import time) — no-op
        self._loop_ref = loop
        self._task = loop.create_task(self._loop())

    def stop(self) -> None:
        # Clear the handle synchronously so a following apply's start() creates a fresh
        # loop; cancel the task thread-safely (stop runs off-loop via set_auto, and
        # cancel() isn't thread-safe). A brief overlap with a freshly started loop is
        # benign — it becomes the single _task and re-writes the same target.
        task, self._task = self._task, None
        loop = self._loop_ref
        if task is None or task.done() or loop is None or loop.is_closed():
            return
        try:
            on_loop = asyncio.get_running_loop() is loop
        except RuntimeError:
            on_loop = False
        if on_loop:
            task.cancel()
        else:
            loop.call_soon_threadsafe(task.cancel)

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(_LOOP_INTERVAL)
                # Off the event loop: _apply_once reads hwmon temp (~ms) and writes
                # the EC/target — blocking I/O that must never sit on the loop that
                # drives the QAM. The 1.5 s cadence is set by the sleep above.
                await asyncio.to_thread(self._apply_once)
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001 — loop must never die
                pass


_DECK_CHIPS = ("steamdeck_hwmon", "jupiter")
_DECK_MAX_RPM = {"Jupiter": 7300, "Galileo": 7300}

# SteamOS runs this systemd service; it continuously RECLAIMS fan1_target,
# overriding our writes. While WE drive a curve we stop it, and restart it on
# release / fail-safe so SteamOS resumes fan control (thermal safety).
_JUPITER_SERVICE = "jupiter-fan-control.service"


def _systemctl_path() -> str:
    """Absolute path to the systemctl binary.

    CRITICAL: the plugin runs under Decky's PyInstaller-frozen PluginLoader, whose
    child process has an EMPTY ``PATH`` (only ``LD_LIBRARY_PATH`` is set to the
    _MEI bundle). So a bare ``["systemctl", …]`` raises FileNotFoundError → our
    guard returns False → jupiter is never stopped and the curve never drives. Use
    an absolute path; fall back through the standard locations, then bare name."""
    for p in ("/usr/bin/systemctl", "/bin/systemctl"):
        if os.path.exists(p):
            return p
    import shutil
    return shutil.which("systemctl") or "systemctl"


def _systemctl(verb: str) -> bool:
    """Run ``systemctl <verb> jupiter-fan-control.service`` as root. Never raises;
    returns True only on exit 0. The plugin runs as root (euid=0).

    CRITICAL — spawn with ``clean_env()``: Decky's PyInstaller-frozen loader sets
    ``LD_LIBRARY_PATH`` to its _MEI bundle (older bundled libcrypto) AND leaves
    ``PATH`` empty. A raw spawn makes systemctl load the bundle's libcrypto →
    ``libsystemd-shared … OPENSSL_x not found`` → rc=1 → jupiter never stops → the
    stored curve never drives at startup. ``clean_env`` restores
    the pre-bundle LD_LIBRARY_PATH + a sane PATH; we also invoke systemctl by
    absolute path. This is the same fix the controller backends use.

    CRITICAL for the ``start`` path: jupiter-fan-control has a systemd start
    rate-limit (StartLimitBurst=5 / StartLimitIntervalUSec=10s). Rapid drive⇄release
    cycles (a user sweeping the curve, mid-session re-fits, lifecycle events) can
    trip it, after which systemd REFUSES to start the unit ("start-limit-hit") and
    the fan is left with NOBODY controlling it — a thermal-safety hole. So before
    every start we ``reset-failed`` to clear the limit counter, guaranteeing jupiter
    can always be brought back. reset-failed on a healthy unit is a harmless no-op."""
    try:
        import subprocess
        from controllers.detect import clean_env
        sc = _systemctl_path()
        env = clean_env()
        if verb == "start":
            subprocess.run([sc, "reset-failed", _JUPITER_SERVICE],
                           check=False, capture_output=True, timeout=10, env=env)
        r = subprocess.run(
            [sc, verb, _JUPITER_SERVICE],
            check=False, capture_output=True, timeout=10, env=env,
        )
        return r.returncode == 0
    except Exception:  # noqa: BLE001 — must never break fan control
        return False


class SteamDeckFanBackend(SoftwareLoopBackend):
    """Steam Deck (LCD/Galileo): write ``fan1_target`` (RPM); release = write 0.

    Std-BIOS retail units need no recalculate handoff — writing fan1_target
    overrides the EC, and 0 hands it back. We re-assert because the EC reclaims.

    SteamOS's ``jupiter-fan-control.service`` also reclaims fan1_target on its own
    ~4 s cadence, so a single write (or our 1.5 s re-assert) loses the tug-of-war
    and the fan ignores the curve. Fix: STOP that service while we drive, and
    RESTART it whenever we release (auto/unload/suspend) — we become the sole fan
    controller only while actively driving. Fail-safe: any release path restarts
    it so the Deck is never left with jupiter stopped and our loop dead.
    """

    def __init__(self, temp_fn=None, root: str = "/", jupiter_ctl=None) -> None:
        super().__init__(temp_fn=temp_fn, root=root)
        board = _read(os.path.join(root, "sys/class/dmi/id/board_name")) or ""
        self.max_rpm = _DECK_MAX_RPM.get(board, 7000)
        # Injectable for tests; defaults to real systemctl.
        self._jupiter_ctl = jupiter_ctl if jupiter_ctl is not None else _systemctl
        self._jupiter_stopped = False  # track state → idempotent (stop/start once)

    def _run_jupiter(self, verb: str) -> bool:
        try:
            return bool(self._jupiter_ctl(verb))
        except Exception:  # noqa: BLE001 — guarded; a broken service mgr must not raise
            return False

    def _before_drive(self) -> bool:
        # Stop jupiter-fan-control once, so it stops fighting our writes. If it
        # won't stop, we don't own the fan → refuse to drive.
        if self._jupiter_stopped:
            return True
        if self._run_jupiter("stop"):
            self._jupiter_stopped = True
            return True
        return False

    def _after_release(self) -> bool:
        # Restart jupiter so SteamOS resumes fan control. Always attempt it
        # (defensively, even if we never stopped it) so we can never leave the
        # Deck with jupiter down. Idempotent: start on a running unit is a no-op.
        # Only clear the "we stopped it" flag if the restart actually succeeded —
        # if it failed, jupiter is still down and read_state/_before_drive must not
        # pretend it's back. reset-failed makes this edge rare. Return whether jupiter
        # is now up so a failed restart makes set_auto report ok=False.
        started = self._run_jupiter("start")
        self._jupiter_stopped = self._jupiter_stopped and not started
        return not self._jupiter_stopped

    @property
    def _owns_fan(self) -> bool:
        # We only truly drive when points are set AND we've taken jupiter down.
        return self._points is not None and self._jupiter_stopped

    def _find_chip(self) -> Optional[str]:
        pattern = os.path.join(self._root, _HWMON, "hwmon*")
        for d in sorted(glob.glob(pattern)):
            if _read(os.path.join(d, "name")) in _DECK_CHIPS:
                if os.path.exists(os.path.join(d, "fan1_target")):
                    self.name = _read(os.path.join(d, "name"))
                    return d
        return None

    def _write_target(self, rpm: int) -> bool:
        return _write(os.path.join(self._dir, "fan1_target"), str(int(rpm)))

    def _release(self) -> bool:
        return _write(os.path.join(self._dir, "fan1_target"), "0")

    def _read_rpm(self) -> Optional[int]:
        return _read_int(os.path.join(self._dir, "fan1_input"))
