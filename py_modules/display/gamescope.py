"""gamescope color control via a generated 3D LUT + `gamescopectl set_look`.

The classic vibrantDeck X-atom path is dead on modern (Wayland) gamescope — xprop
can't reach the X server. The working mechanism is a `.cube` 3D LUT loaded through
gamescope's Wayland control socket: `XDG_RUNTIME_DIR=/run/user/<uid>
WAYLAND_DISPLAY=gamescope-0 gamescopectl set_look <file>` (needs root).

The color transform (transform/build_cube) is pure; the socket discovery + subprocess
call is the thin device layer. Unsupported (UI hidden) when no gamescope socket answers."""
import glob
import math
import os
import re
import subprocess
import tempfile
import time

from display.const import NATIVE as _NATIVE
from display.const import LOOK_FIELDS as _LOOK_FIELDS
from display.edid import supports_pq
from display.hdr_color import build_hdr_cube

_LUT_SIZE = 17  # 17^3 grid — smooth enough for color, cheap to generate/apply
_PROBE_RETRY_S = 5.0  # min interval between probes of a present-but-unresponsive socket

# Rec.709 luma weights (saturation pivots around perceived brightness).
_LR, _LG, _LB = 0.2126, 0.7152, 0.0722
_TEMP_GAIN = 0.3     # temperature push at ±100
_HUE_MAX_DEG = 30.0  # hue rotation at ±100
_BLACK_MAX = 0.15    # black-point shift at ±100


def _clamp01(v):
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def _toward_luma(r, g, b, f):
    """Scale each channel's distance from its luma by f (f=0 → grey, 1 → unchanged,
    >1 → more saturated). The shared core of saturation and vibrance."""
    y = _LR * r + _LG * g + _LB * b
    return y + f * (r - y), y + f * (g - y), y + f * (b - y)


def _black(v, k):
    """Shift the black point by k in (-1, 1). k>0 raises it (greyer blacks, more shadow
    detail); k<0 deepens it (crushes near-blacks). White (1) is left fixed either way."""
    return k + (1.0 - k) * v if k >= 0.0 else (v + k) / (1.0 + k)


def _gpow(v, exp):
    """Gamma on one channel; base clamped >=0 so a fractional exponent never returns
    a complex number (endpoints 0 and 1 stay fixed)."""
    return (v if v <= 0.0 else v ** exp)


def _hue_matrix(deg):
    """Luma-preserving hue-rotation matrix (SVG feColorMatrix); every row sums to 1 so
    grey is unchanged."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (
        (0.213 + c * 0.787 - s * 0.213, 0.715 - c * 0.715 - s * 0.715, 0.072 - c * 0.072 + s * 0.928),
        (0.213 - c * 0.213 + s * 0.143, 0.715 + c * 0.285 + s * 0.140, 0.072 - c * 0.072 - s * 0.283),
        (0.213 - c * 0.213 - s * 0.787, 0.715 - c * 0.715 + s * 0.715, 0.072 + c * 0.928 + s * 0.072),
    )


def _coeffs(state):
    """Precompute the per-look coefficients once — they're invariant across the LUT, so
    build_cube derives them a single time rather than re-reading `state` per node."""
    gm, h, bl = state.get("gamma", 0), state.get("hue", 0), state.get("black", 0)
    return (
        state.get("gain_r", 100) / 100.0,
        state.get("gain_g", 100) / 100.0,
        state.get("gain_b", 100) / 100.0,
        state.get("temperature", 0) / 100.0,
        (2.0 ** (-gm / 100.0)) if gm else None,          # gamma exponent
        state.get("saturation", 100) / 100.0,
        state.get("vibrance", 0) / 100.0,
        _hue_matrix(h * _HUE_MAX_DEG / 100.0) if h else None,
        1.0 + state.get("contrast", 0) / 100.0,          # contrast k
        (bl / 100.0 * _BLACK_MAX) if bl else None,        # black-point shift
    )


def _apply(r, g, b, c):
    """Apply precomputed coefficients to one (r,g,b). Order: per-channel gain →
    temperature → gamma → saturation → vibrance (spares vivid pixels) → hue → contrast
    → black point. All outputs clamped 0..1."""
    gr, gg, gb, t, gexp, s, v, hmat, k, kb = c
    r, g, b = r * gr, g * gg, b * gb
    r *= 1.0 + _TEMP_GAIN * t
    b *= 1.0 - _TEMP_GAIN * t
    if gexp is not None:
        r, g, b = _gpow(r, gexp), _gpow(g, gexp), _gpow(b, gexp)
    r, g, b = _toward_luma(r, g, b, s)
    if v:
        sat = max(r, g, b) - min(r, g, b)
        r, g, b = _toward_luma(r, g, b, 1.0 + v * (1.0 - _clamp01(sat)))
    if hmat is not None:
        (m00, m01, m02), (m10, m11, m12), (m20, m21, m22) = hmat
        r, g, b = (m00 * r + m01 * g + m02 * b,
                   m10 * r + m11 * g + m12 * b,
                   m20 * r + m21 * g + m22 * b)
    r, g, b = (r - 0.5) * k + 0.5, (g - 0.5) * k + 0.5, (b - 0.5) * k + 0.5
    if kb is not None:
        r, g, b = _black(r, kb), _black(g, kb), _black(b, kb)
    return _clamp01(r), _clamp01(g), _clamp01(b)


def transform(r, g, b, state):
    """Apply the color look to one (r,g,b) in 0..1. A native state is the identity.

    temperature/contrast/gamma/hue/vibrance/black: -100..+100 (0 neutral). gain_r/g/b:
    50..150 (100 = 1.0). saturation: 0 grayscale .. 100 neutral .. 200 vivid."""
    return _apply(r, g, b, _coeffs(state))


def build_cube(state, size=_LUT_SIZE):
    """A .cube 3D LUT text realising `state` (red index varies fastest — .cube spec)."""
    n = size - 1
    c = _coeffs(state)
    lines = ['TITLE "panel-de-control"', f"LUT_3D_SIZE {size}"]
    for bi in range(size):
        for gi in range(size):
            for ri in range(size):
                ro, go, bo = _apply(ri / n, gi / n, bi / n, c)
                lines.append(f"{ro:.5f} {go:.5f} {bo:.5f}")
    return "\n".join(lines) + "\n"


def is_native(state):
    return all(state.get(f, v) == v for f, v in _NATIVE.items())


def _run(args, env):
    try:
        # Resolve the binary absolutely + start from clean_env (restores the
        # pre-bundle LD_LIBRARY_PATH + a sane PATH that Decky's frozen loader
        # strips), then overlay the caller's Wayland env (XDG_RUNTIME_DIR /
        # WAYLAND_DISPLAY). Same spawn hygiene as the controller/fan backends.
        from controllers.detect import clean_env, resolve_bin
        argv = [resolve_bin(args[0]), *args[1:]]
        # Short timeout: this runs on the event loop, so it must fail fast rather than
        # stall it if gamescope is wedged (the calls themselves complete in ms).
        p = subprocess.run(argv, capture_output=True, text=True, timeout=2,
                           env={**clean_env(), **env})
        return p.returncode, (p.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def run_gamescopectl(args, socket_glob="/run/user/*/gamescope-*"):
    """Run `gamescopectl <args>` against the live gamescope Wayland socket. Returns
    (rc, stdout); rc=1 when no socket is present. Used by the HDR backend."""
    for sock in sorted(glob.glob(socket_glob)):
        wayland_display = os.path.basename(sock)
        env = {
            "XDG_RUNTIME_DIR": os.path.dirname(sock),
            "WAYLAND_DISPLAY": wayland_display,
            "GAMESCOPE_WAYLAND_DISPLAY": wayland_display,
        }
        return _run(["gamescopectl", *args], env)
    return 1, ""


class GamescopeColorBackend:
    """Applies color via `gamescopectl set_look`. Discovers the gamescope Wayland
    socket under /run/user/*/gamescope-*; probe-gated on `gamescopectl` responding.
    `runner(args, env) -> (rc, stdout)` is injected for testing."""

    def __init__(self, runner=_run, socket_glob="/run/user/*/gamescope-*", lut_path=None,
                 force_composite=False, clock=time.monotonic,
                 hdr_look=False, edid_pq=None,
                 drm_root="/sys/class/drm"):
        self._run = runner
        # On Intel/Xe the color LUT is only applied while gamescope COMPOSITES (it's
        # not carried by the HW DRM color pipeline as on AMD), so a look is invisible
        # during direct scanout (in-game). force_composite makes apply() toggle
        # gamescope's composite_force convar so the look is visible in-game too — at a
        # small power cost (composition every frame). AMD leaves this False.
        self._force_composite = force_composite
        self._hdr_look_requested = bool(hdr_look)
        self._hdr_look_supported = False
        self._hdr_look_detail = "not requested"
        self._active_connector = None
        self._drm_root = drm_root
        self._edid_pq = edid_pq or self._connector_supports_pq
        self._lut_path = lut_path or os.path.join(tempfile.gettempdir(), "pdc_look.cube")
        base, extension = os.path.splitext(self._lut_path)
        self._g22_paths = (
            self._lut_path,
            f"{base}.next{extension}",
        )
        self._pq_paths = (
            f"{base}.pq{extension}",
            f"{base}.pq.next{extension}",
        )
        self._pair_index = 0
        # The socket may not exist yet when the plugin loads, so probe on demand.
        self._socket_glob = socket_glob
        self._clock = clock
        self._last_probe = None
        self._runtime = self._wayland = None
        self._session_identity = None
        self._supported = False
        # Last probe outcome, for diagnostics (a report showing the UI hidden should
        # say WHY: no socket / gamescopectl rc). Never affects `supported`.
        self._probe_detail = "not probed"
        self._managed = False
        self._managed_paired = False
        self._composite_managed = False
        self._last_paths = None
        self._last_desired = None
        self._last_apply = None
        self._ensure_supported()

    def _discover(self, pattern):
        for sock in sorted(glob.glob(pattern)):
            return os.path.dirname(sock), os.path.basename(sock)
        return None, None

    @staticmethod
    def _socket_identity(runtime, wayland):
        if runtime is None or wayland is None:
            return None
        try:
            stat = os.stat(os.path.join(runtime, wayland))
        except OSError:
            return None
        return stat.st_dev, stat.st_ino

    def _refresh_session_identity(self):
        runtime, wayland = self._discover(self._socket_glob)
        identity = self._socket_identity(runtime, wayland)
        if identity is None:
            if self._session_identity is not None:
                self._managed = False
                self._managed_paired = False
                self._composite_managed = False
                self._last_paths = None
            self._runtime = self._wayland = None
            self._session_identity = None
            self._supported = False
            self._probe_detail = (
                f"no gamescope socket under {self._socket_glob}"
            )
            return False
        session = runtime, wayland, identity
        previous = (
            self._runtime, self._wayland, self._session_identity
        )
        if session != previous:
            had_session = self._session_identity is not None
            self._runtime = runtime
            self._wayland = wayland
            self._session_identity = identity
            self._supported = False
            self._last_probe = None
            self._hdr_look_supported = False
            self._active_connector = None
            if had_session:
                self._managed = False
                self._managed_paired = False
                self._composite_managed = False
                self._last_paths = None
        return True

    def _ctl(self, *args):
        env = {
            "XDG_RUNTIME_DIR": self._runtime,
            "WAYLAND_DISPLAY": self._wayland,
            "GAMESCOPE_WAYLAND_DISPLAY": self._wayland,
        }
        return self._run(["gamescopectl", *args], env)

    def _probe(self):
        rc, _ = self._ctl("version")
        self._probe_detail = f"socket={self._runtime}/{self._wayland} version rc={rc}"
        if rc == 0 and self._hdr_look_requested:
            self._probe_hdr_look()
        return rc == 0

    def _probe_hdr_look(self):
        rc, output = self._ctl()
        feature = re.search(
            r"^\s*-\s+[^\r\n]*\(6\)\s+-\s+Version:\s+(\d+)",
            output or "",
            re.MULTILINE,
        )
        flags_match = re.search(
            r"Display Flags: 0x([0-9a-fA-F]+)", output or ""
        )
        connector = re.search(
            r"Connector Name: ([^\r\n]+)", output or ""
        )
        flags = int(flags_match.group(1), 16) if flags_match else 0
        self._active_connector = (
            connector.group(1).strip() if connector else None
        )
        edid_pq = bool(
            self._active_connector
            and self._edid_pq(self._active_connector)
        )
        self._hdr_look_supported = bool(
            rc == 0
            and feature
            and int(feature.group(1)) >= 1
            and flags & 0x3 == 0x3
            and edid_pq
        )
        self._hdr_look_detail = (
            f"info rc={rc} look={feature.group(1) if feature else 'missing'} "
            f"display_flags=0x{flags:x} connector={self._active_connector or 'unknown'} "
            f"edid_pq={edid_pq}"
        )

    def _refresh_hdr_look(self):
        if not self._hdr_look_requested:
            return
        try:
            self._probe_hdr_look()
        except (OSError, TypeError, ValueError) as error:
            self._hdr_look_supported = False
            self._active_connector = None
            self._hdr_look_detail = (
                f"active display probe failed: {type(error).__name__}"
            )

    def _connector_supports_pq(self, connector):
        escaped = glob.escape(connector)
        paths = glob.glob(os.path.join(
            self._drm_root, f"card*-{escaped}", "edid"
        ))
        if len(paths) != 1:
            return False
        try:
            with open(paths[0], "rb") as edid:
                return supports_pq(edid.read())
        except OSError:
            return False

    def _ensure_supported(self):
        """Discover the socket + probe on demand, caching the first success."""
        if not self._refresh_session_identity():
            return False
        if self._supported:
            return True
        # Rate-limit the probe: it spawns a subprocess and is read on the event loop,
        # so a present-but-unresponsive socket must not re-probe on every access.
        now = self._clock()
        if self._last_probe is not None and now - self._last_probe < _PROBE_RETRY_S:
            return False
        self._last_probe = now
        self._supported = self._probe()
        return self._supported

    def _invalidate_session(self, rc):
        self._supported = False
        self._last_probe = None
        self._hdr_look_supported = False
        self._active_connector = None
        self._probe_detail = f"gamescope session invalidated after set_look rc={rc}"
        self._hdr_look_detail = "session invalidated; awaiting reprobe"

    @property
    def supported(self):
        return self._ensure_supported()

    @property
    def probe_detail(self):
        """Last support-probe outcome (missing socket, or gamescopectl version rc).
        Logged once so a report with the Pantalla tab hidden is diagnosable."""
        return self._probe_detail

    @property
    def force_composite(self):
        """True when applying a look here forces gamescope composition (Intel/Xe) —
        i.e. a look costs a bit of extra power on this device. The UI notes it."""
        return self._force_composite

    @property
    def hdr_look_supported(self):
        if self._ensure_supported():
            self._refresh_hdr_look()
        return self._hdr_look_supported

    @property
    def session_identity(self):
        self._refresh_session_identity()
        return self._session_identity

    def diagnostics(self):
        return {
            "supported": self.supported,
            "probe_detail": self._probe_detail,
            "wayland_display": self._wayland,
            "hdr_look_supported": self._hdr_look_supported,
            "hdr_look_detail": self._hdr_look_detail,
            "active_connector": self._active_connector,
            "managed": self._managed,
            "composite_managed": self._composite_managed,
            "session_identity": self._session_identity,
            "look_paths": dict(self._last_paths) if self._last_paths else None,
            "desired": dict(self._last_desired) if self._last_desired else None,
            "last_apply": dict(self._last_apply) if self._last_apply else None,
        }

    def display_fingerprint(self):
        if not self._ensure_supported():
            return self._session_identity, None, False
        self._refresh_hdr_look()
        return (
            self._session_identity,
            self._active_connector,
            self._hdr_look_supported,
        )

    @staticmethod
    def _write_atomic(path, content):
        directory = os.path.dirname(path) or "."
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=directory, delete=False
            ) as output:
                temporary = output.name
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        except OSError:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
            raise

    def release(self):
        if not self._managed and not self._composite_managed:
            return True
        if not self._ensure_supported():
            return False
        if self._managed:
            rc, _ = self._ctl("unset_look")
            self._last_apply = {
                "operation": "unset_look", "ok": rc == 0, "rc": rc,
            }
            if rc != 0:
                self._invalidate_session(rc)
                return False
            self._managed = False
            self._managed_paired = False
            self._last_paths = None
        if self._composite_managed:
            rc, _ = self._ctl("composite_force", "0")
            if rc != 0:
                self._last_apply = {
                    "operation": "composite_force",
                    "enabled": False,
                    "ok": False,
                    "rc": rc,
                }
                return False
            self._composite_managed = False
        return True

    def apply(self, state):
        """Load the effective look without touching a look this instance does not own."""
        if not self._ensure_supported():
            return False
        self._refresh_hdr_look()
        g22_native = all(
            state.get(field, _NATIVE[field]) == _NATIVE[field]
            for field in _LOOK_FIELDS
        )
        paired = self._hdr_look_supported
        pq_native = state.get("hdr_saturation", 100) == 100
        native = g22_native and (pq_native if paired else True)
        self._last_desired = {
            **{field: state.get(field, _NATIVE[field]) for field in _LOOK_FIELDS},
            "hdr_saturation": state.get("hdr_saturation", 100),
            "paired": paired,
        }
        if self._managed and self._managed_paired and not paired:
            if not self.release():
                return False
        if native:
            return self.release()
        composite_enabled_here = False
        try:
            if self._force_composite and not self._composite_managed:
                composite_rc, _ = self._ctl("composite_force", "1")
                if composite_rc != 0:
                    self._last_apply = {
                        "operation": "composite_force",
                        "enabled": True,
                        "ok": False,
                        "rc": composite_rc,
                    }
                    return False
                self._composite_managed = True
                composite_enabled_here = True
            pair_index = self._pair_index if paired else 0
            g22_path = self._g22_paths[pair_index]
            self._write_atomic(g22_path, build_cube(state))
            paths = {"g22": g22_path, "pq": None}
            if paired:
                pq_path = self._pq_paths[pair_index]
                self._write_atomic(
                    pq_path,
                    build_hdr_cube(state.get("hdr_saturation", 100)),
                )
                paths["pq"] = pq_path
                rc, _ = self._ctl("set_look", g22_path, pq_path)
            else:
                rc, _ = self._ctl("set_look", g22_path)
            self._last_apply = {"operation": "set_look", "ok": rc == 0, "rc": rc}
            if rc == 0:
                self._managed = True
                self._managed_paired = paired
                self._last_paths = paths
                if paired:
                    self._pair_index = 1 - pair_index
            else:
                self._invalidate_session(rc)
                if composite_enabled_here:
                    rollback_rc, _ = self._ctl("composite_force", "0")
                    if rollback_rc == 0:
                        self._composite_managed = False
                    self._last_apply["composite_rollback"] = (
                        rollback_rc == 0
                    )
            return rc == 0
        except OSError:
            self._last_apply = {"operation": "set_look", "ok": False, "rc": None}
            if composite_enabled_here:
                rollback_rc, _ = self._ctl("composite_force", "0")
                if rollback_rc == 0:
                    self._composite_managed = False
                self._last_apply["composite_rollback"] = rollback_rc == 0
            return False
