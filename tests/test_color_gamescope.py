from display.gamescope import (
    _PROBE_RETRY_S,
    GamescopeColorBackend,
    build_cube,
    is_native,
    transform,
)

NATIVE = {"saturation": 100, "temperature": 0, "contrast": 0}

_PTS = [(0.0, 0.0, 0.0), (0.5, 0.3, 0.7), (1.0, 1.0, 1.0), (0.8, 0.2, 0.4)]


def _close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ---- pure color transform ----

def test_native_transform_is_identity():
    for p in _PTS:
        assert _close(transform(*p, NATIVE), p)


def test_saturation_zero_is_grayscale():
    r, g, b = transform(0.8, 0.2, 0.4, {**NATIVE, "saturation": 0})
    assert _close((r, g), (r, r)) and _close((r, b), (r, r))  # all channels equal (luma)


def test_saturation_boost_pushes_away_from_luma():
    base = transform(0.7, 0.3, 0.5, NATIVE)
    hot = transform(0.7, 0.3, 0.5, {**NATIVE, "saturation": 160})
    assert max(hot) >= max(base) and min(hot) <= min(base)


def test_temperature_warm_raises_red_lowers_blue():
    r, g, b = transform(0.5, 0.5, 0.5, {**NATIVE, "temperature": 100})
    assert r > 0.5 and b < 0.5 and _close((g,), (0.5,))


def test_temperature_cool_lowers_red_raises_blue():
    r, g, b = transform(0.5, 0.5, 0.5, {**NATIVE, "temperature": -100})
    assert r < 0.5 and b > 0.5


def test_contrast_positive_spreads_around_mid():
    hi = transform(0.7, 0.7, 0.7, {**NATIVE, "contrast": 100})
    lo = transform(0.3, 0.3, 0.3, {**NATIVE, "contrast": 100})
    assert hi[0] > 0.7 and lo[0] < 0.3  # pushed apart


def test_contrast_negative_flattens_toward_mid():
    hi = transform(0.9, 0.9, 0.9, {**NATIVE, "contrast": -100})
    assert hi[0] < 0.9 and hi[0] >= 0.5  # pulled toward 0.5


def test_endpoints_and_all_outputs_clamped_0_1():
    for st in [{**NATIVE, "saturation": 200, "temperature": 100},
               {**NATIVE, "contrast": 100}, {**NATIVE, "contrast": -100}]:
        for p in _PTS:
            for v in transform(*p, st):
                assert 0.0 <= v <= 1.0


# ---- .cube generation ----

def test_build_cube_header_and_size():
    text = build_cube(NATIVE, size=5)
    assert "LUT_3D_SIZE 5" in text
    assert sum(1 for ln in text.splitlines() if len(ln.split()) == 3 and ln[0].isdigit()) == 125


def test_is_native():
    assert is_native(NATIVE) is True
    assert is_native({**NATIVE, "saturation": 120}) is False
    assert is_native({**NATIVE, "contrast": 10}) is False


# ---- backend (injected runner + fake socket) ----

class FakeRunner:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def __call__(self, args, env):
        self.calls.append((args, env))
        return (0 if self.ok else 1, "gamescope version 3.16" if self.ok else "")


def _backend(tmp_path, ok=True, force_composite=False):
    sock = tmp_path / "run" / "user" / "1000" / "gamescope-0"
    sock.parent.mkdir(parents=True)
    sock.write_text("")
    r = FakeRunner(ok=ok)
    b = GamescopeColorBackend(runner=r, socket_glob=str(tmp_path / "run/user/*/gamescope-*"),
                              lut_path=str(tmp_path / "look.cube"), force_composite=force_composite)
    return b, r


def _composite_calls(runner):
    return [c[0] for c in runner.calls if c[0][:2] == ["gamescopectl", "composite_force"]]


def test_backend_supported_when_gamescopectl_responds(tmp_path):
    b, r = _backend(tmp_path)
    assert b.supported is True
    _, env = r.calls[0]
    assert env["WAYLAND_DISPLAY"] == "gamescope-0" and env["XDG_RUNTIME_DIR"].endswith("/1000")


def test_backend_unsupported_when_no_socket(tmp_path):
    (tmp_path / "run").mkdir()
    b = GamescopeColorBackend(runner=FakeRunner(),
                              socket_glob=str(tmp_path / "run/user/*/gamescope-*"))
    assert b.supported is False
    assert b.apply({**NATIVE, "saturation": 150}) is False


def test_backend_self_heals_when_socket_appears_after_init(tmp_path):
    # A socket that appears after construction must still be picked up.
    run = tmp_path / "run"
    run.mkdir()
    r = FakeRunner(ok=True)
    b = GamescopeColorBackend(runner=r,
                              socket_glob=str(tmp_path / "run/user/*/gamescope-*"),
                              lut_path=str(tmp_path / "look.cube"))
    assert b.supported is False            # no socket yet at construction
    sock = run / "user" / "1000" / "gamescope-0"
    sock.parent.mkdir(parents=True)
    sock.write_text("")
    assert b.supported is True             # gamescope came up → re-discovered + probed
    assert b.apply({**NATIVE, "saturation": 150}) is True


def test_backend_rate_limits_probe_of_unresponsive_socket(tmp_path):
    # A socket that exists but doesn't answer must not re-spawn the probe on every read.
    sock = tmp_path / "run" / "user" / "1000" / "gamescope-0"
    sock.parent.mkdir(parents=True)
    sock.write_text("")
    r = FakeRunner(ok=False)
    t = [100.0]
    b = GamescopeColorBackend(runner=r, socket_glob=str(tmp_path / "run/user/*/gamescope-*"),
                              lut_path=str(tmp_path / "look.cube"), clock=lambda: t[0])

    def probes():
        return len([c for c in r.calls if c[0][:2] == ["gamescopectl", "version"]])

    assert b.supported is False and probes() == 1   # probed once at construction
    assert b.supported is False and probes() == 1   # within backoff → no re-probe
    t[0] += _PROBE_RETRY_S + 1
    assert b.supported is False and probes() == 2   # past the interval → re-probes


def test_backend_apply_writes_cube_and_calls_set_look(tmp_path):
    b, r = _backend(tmp_path)
    r.calls.clear()
    assert b.apply({**NATIVE, "saturation": 150}) is True
    setlook = [c for c in r.calls if c[0][:2] == ["gamescopectl", "set_look"]]
    assert len(setlook) == 1
    path = setlook[0][0][2]
    assert path.endswith("look.cube")
    assert "LUT_3D_SIZE" in open(path).read()


def _setlooks(runner):
    return [c for c in runner.calls if c[0][:2] == ["gamescopectl", "set_look"]]


def test_backend_no_composite_force_when_not_needed(tmp_path):
    # AMD path: the HW color pipeline applies the LUT → never touch composite_force.
    b, r = _backend(tmp_path, force_composite=False)
    r.calls.clear()
    b.apply({**NATIVE, "saturation": 150})
    assert _composite_calls(r) == []


def test_backend_forces_composition_for_nonnative_and_clears_on_native(tmp_path):
    # Intel/Xe path: the LUT only applies while gamescope composites, so force it on
    # for a non-native look and off when returning to native.
    b, r = _backend(tmp_path, force_composite=True)
    r.calls.clear()
    b.apply({**NATIVE, "saturation": 150})
    assert ["gamescopectl", "composite_force", "1"] in _composite_calls(r)
    r.calls.clear()
    b.apply(NATIVE)
    assert ["gamescopectl", "composite_force", "0"] in _composite_calls(r)


def test_backend_clears_leftover_once_then_skips_native(tmp_path):
    # A fresh backend assumes a prior process may have left a look → the FIRST native
    # apply clears it once; subsequent native applies are no-ops (no wasted set_look).
    b, r = _backend(tmp_path)
    r.calls.clear()
    assert b.apply(NATIVE) is True
    assert len(_setlooks(r)) == 1   # cleared the (possible) leftover once
    r.calls.clear()
    assert b.apply(NATIVE) is True
    assert _setlooks(r) == []       # already native → skipped


def test_backend_clears_look_once_when_returning_to_native(tmp_path):
    b, r = _backend(tmp_path)
    b.apply({**NATIVE, "saturation": 150})  # non-native → loaded
    r.calls.clear()
    assert b.apply(NATIVE) is True          # returns to native → clears once
    assert len(_setlooks(r)) == 1
    r.calls.clear()
    assert b.apply(NATIVE) is True          # already native → skipped
    assert _setlooks(r) == []
