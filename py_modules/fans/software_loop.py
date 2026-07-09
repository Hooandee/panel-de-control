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


class SoftwareLoopBackend:
    """Base: owns the stored curve, the asyncio re-assert loop, and duty→RPM."""

    name = "software-loop"
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
        self._task: Optional[asyncio.Task] = None
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

    def _after_release(self) -> None:
        """Hand ownership back after releasing the fan (fail-safe). Override to
        restart a stopped daemon. Default: no-op."""
        return None

    @property
    def _owns_fan(self) -> bool:
        """True only when we actually drive the fan (points set AND ownership
        acquired). read_state reports manual only when this holds."""
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
        return {"supported": True, "source": self.name, "pwm_max": 255,
                "fans": [{"key": "fan", "enable": 1 if self._owns_fan else 2,
                          "rpm": rpm, "points": []}]}

    def apply_curve_all(self, points: list) -> dict:
        if not self.supported:
            return {"ok": False, "detail": f"{self.name} not found"}
        # Take ownership of the fan FIRST. If we can't (e.g. jupiter-fan-control
        # refused to stop), we do NOT own the fan → never claim to drive and
        # never write a target the OS daemon would fight.
        if not self._before_drive():
            return {"ok": False, "detail": f"{self.name} could not take fan control"}
        self._points = [list(p) for p in sanitize_curve(points)]
        self._apply_once()   # immediate response, before the loop's first tick
        self.start()
        return {"ok": True, "detail": f"{self.name} curve applied (software loop)"}

    def set_curve(self, fan_key, points: list) -> dict:
        return self.apply_curve_all(points)

    def set_auto(self, fan_key: Optional[str] = None) -> dict:
        if not self.supported:
            return {"ok": False, "detail": f"{self.name} not found"}
        # Clear points FIRST so any in-flight loop tick computes target_for_temp→None
        # and writes nothing, then stop the loop and release. (A full fix awaits the
        # cancelled task — deferred async cancel+await, shared with the sampler.)
        self._points = None
        self.stop()
        # Under the lock, so a tick already mid-write finishes FIRST and our release
        # write lands last — the fan is never left driven after we release it.
        with self._io_lock:
            ok = self._release()
        # Hand ownership back to the OS/firmware daemon LAST (fail-safe: even if
        # the target write failed, the device must never be left with our loop
        # dead AND the daemon stopped).
        self._after_release()
        return {"ok": ok, "detail": "released to firmware" if ok else "release write failed"}

    def restore_auto(self) -> dict:
        return self.set_auto(None)

    # --- the loop --------------------------------------------------------------
    def _apply_once(self) -> None:
        # Locked so a release (set_auto) can't interleave with this write: once we
        # start writing, the release waits for us, then wins (target released).
        with self._io_lock:
            temp = self._temp_fn() if self._temp_fn else None
            target = self.target_for_temp(temp)
            if target is not None:
                self._write_target(target)

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no event loop (tests / import time) — no-op
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

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

    def _after_release(self) -> None:
        # Restart jupiter so SteamOS resumes fan control. Always attempt it
        # (defensively, even if we never stopped it) so we can never leave the
        # Deck with jupiter down. Idempotent: start on a running unit is a no-op.
        # Only clear the "we stopped it" flag if the restart actually succeeded —
        # if it failed, jupiter is still down and read_state/_before_drive must not
        # pretend it's back. reset-failed makes this edge rare.
        started = self._run_jupiter("start")
        self._jupiter_stopped = self._jupiter_stopped and not started

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
