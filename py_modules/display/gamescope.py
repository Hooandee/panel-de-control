"""gamescope color control via a generated 3D LUT + `gamescopectl set_look`.

The classic vibrantDeck X-atom path is dead on modern (Wayland) gamescope — xprop
can't reach the X server. The working mechanism is a `.cube` 3D LUT loaded through
gamescope's Wayland control socket: `XDG_RUNTIME_DIR=/run/user/<uid>
WAYLAND_DISPLAY=gamescope-0 gamescopectl set_look <file>` (needs root).

The color transform (transform/build_cube) is pure; the socket discovery + subprocess
call is the thin device layer. Unsupported (UI hidden) when no gamescope socket answers."""
import glob
import os
import subprocess
import tempfile
import time

from display.const import NATIVE as _NATIVE

_LUT_SIZE = 17  # 17^3 grid — smooth enough for color, cheap to generate/apply
_PROBE_RETRY_S = 5.0  # min interval between probes of a present-but-unresponsive socket

# Rec.709 luma weights (saturation pivots around perceived brightness).
_LR, _LG, _LB = 0.2126, 0.7152, 0.0722
# How hard the extreme temperature/contrast ends push (kept tasteful, not garish).
_TEMP_GAIN = 0.3


def _clamp01(v):
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def transform(r, g, b, state):
    """Apply the color look to one (r,g,b) in 0..1. Order: temperature (warm↔cool
    white balance) → saturation (around luma) → contrast (around mid-grey). All
    outputs clamped 0..1; a native state is the identity.

    temperature: -100 cool .. +100 warm (0 neutral). contrast: -100 flat .. +100
    punchy (0 neutral). saturation: 0 grayscale .. 100 neutral .. 200 vivid."""
    # temperature: warm (>0) raises red, lowers blue; cool (<0) the reverse.
    t = state.get("temperature", 0) / 100.0
    r *= 1.0 + _TEMP_GAIN * t
    b *= 1.0 - _TEMP_GAIN * t
    # saturation around luma.
    s = state.get("saturation", 100) / 100.0
    y = _LR * r + _LG * g + _LB * b
    r, g, b = y + s * (r - y), y + s * (g - y), y + s * (b - y)
    # contrast around mid-grey (0.5). k in 0..2 (1 = neutral).
    k = 1.0 + state.get("contrast", 0) / 100.0
    r, g, b = (r - 0.5) * k + 0.5, (g - 0.5) * k + 0.5, (b - 0.5) * k + 0.5
    return _clamp01(r), _clamp01(g), _clamp01(b)


def build_cube(state, size=_LUT_SIZE):
    """A .cube 3D LUT text realising `state` (red index varies fastest — .cube spec)."""
    n = size - 1
    lines = ['TITLE "panel-de-control"', f"LUT_3D_SIZE {size}"]
    for bi in range(size):
        for gi in range(size):
            for ri in range(size):
                ro, go, bo = transform(ri / n, gi / n, bi / n, state)
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


class GamescopeColorBackend:
    """Applies color via `gamescopectl set_look`. Discovers the gamescope Wayland
    socket under /run/user/*/gamescope-*; probe-gated on `gamescopectl` responding.
    `runner(args, env) -> (rc, stdout)` is injected for testing."""

    def __init__(self, runner=_run, socket_glob="/run/user/*/gamescope-*", lut_path=None,
                 force_composite=False, clock=time.monotonic):
        self._run = runner
        # On Intel/Xe the color LUT is only applied while gamescope COMPOSITES (it's
        # not carried by the HW DRM color pipeline as on AMD), so a look is invisible
        # during direct scanout (in-game). force_composite makes apply() toggle
        # gamescope's composite_force convar so the look is visible in-game too — at a
        # small power cost (composition every frame). AMD leaves this False.
        self._force_composite = force_composite
        self._lut_path = lut_path or os.path.join(tempfile.gettempdir(), "pdc_look.cube")
        # The socket may not exist yet when the plugin loads, so probe on demand.
        self._socket_glob = socket_glob
        self._clock = clock
        self._last_probe = None
        self._runtime = self._wayland = None
        self._supported = False
        self._ensure_supported()
        # Whether a non-native look may be loaded — lets apply() skip rebuilding the
        # identity LUT on the common (untouched-color) path, yet still clear a look
        # exactly once when returning to native. Starts True: a prior plugin process
        # (or a crash) may have left a look loaded in gamescope that this fresh process
        # can't see, so the FIRST apply always runs (clearing any leftover); it settles
        # to False once native is applied.
        self._applied_non_native = True

    def _discover(self, pattern):
        for sock in sorted(glob.glob(pattern)):
            return os.path.dirname(sock), os.path.basename(sock)
        return None, None

    def _ctl(self, *args):
        env = {"XDG_RUNTIME_DIR": self._runtime, "WAYLAND_DISPLAY": self._wayland}
        return self._run(["gamescopectl", *args], env)

    def _probe(self):
        rc, _ = self._ctl("version")
        return rc == 0

    def _ensure_supported(self):
        """Discover the socket + probe on demand, caching the first success."""
        if self._supported:
            return True
        self._runtime, self._wayland = self._discover(self._socket_glob)
        if self._runtime is None:
            return False
        # Rate-limit the probe: it spawns a subprocess and is read on the event loop,
        # so a present-but-unresponsive socket must not re-probe on every access.
        now = self._clock()
        if self._last_probe is not None and now - self._last_probe < _PROBE_RETRY_S:
            return False
        self._last_probe = now
        self._supported = self._probe()
        return self._supported

    @property
    def supported(self):
        return self._ensure_supported()

    @property
    def force_composite(self):
        """True when applying a look here forces gamescope composition (Intel/Xe) —
        i.e. a look costs a bit of extra power on this device. The UI notes it."""
        return self._force_composite

    def apply(self, state):
        """Write the LUT for `state` and load it via set_look. A native state loads
        the identity LUT to clear a prior look — but is skipped entirely when nothing
        non-native is currently applied (no wasted rebuild on the untouched path).
        On force_composite devices, toggles gamescope composition so the look is
        visible in-game (on for a look, off at native). Never raises."""
        if not self._ensure_supported():
            return False
        native = is_native(state)
        if native and not self._applied_non_native:
            return True  # already native / nothing loaded → nothing to do
        try:
            # Intel/Xe: composite so the LUT is visible in-game (off again at native).
            if self._force_composite:
                self._ctl("composite_force", "0" if native else "1")
            with open(self._lut_path, "w") as f:
                f.write(build_cube(state))
            rc, _ = self._ctl("set_look", self._lut_path)
            if rc == 0:
                self._applied_non_native = not native
            return rc == 0
        except OSError:
            return False
