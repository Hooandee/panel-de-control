import os

from display.const import NATIVE
from display.gamescope import (
    _PROBE_RETRY_S,
    GamescopeColorBackend,
    build_cube,
    is_native,
    transform,
)
from display.hdr import _UNAVAILABLE_LOOK

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
               {**NATIVE, "contrast": 100}, {**NATIVE, "contrast": -100},
               {**NATIVE, "gamma": 100, "gain_r": 150, "gain_b": 150},
               {**NATIVE, "gamma": -100}, {**NATIVE, "hue": 100, "saturation": 200},
               {**NATIVE, "vibrance": 100, "saturation": 200},
               {**NATIVE, "black": 100}, {**NATIVE, "black": -100, "contrast": -60}]:
        for p in _PTS:
            for v in transform(*p, st):
                assert 0.0 <= v <= 1.0


# ---- advanced color fields (all missing => neutral, so pre-existing states are safe) ----

def test_gamma_positive_brightens_midtones():
    r, _, _ = transform(0.5, 0.5, 0.5, {**NATIVE, "gamma": 100})
    assert r > 0.5


def test_gamma_negative_darkens_midtones():
    r, _, _ = transform(0.5, 0.5, 0.5, {**NATIVE, "gamma": -100})
    assert r < 0.5


def test_gamma_leaves_endpoints_fixed():
    for p in [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)]:
        assert _close(transform(*p, {**NATIVE, "gamma": 80}), p, tol=1e-4)


def test_rgb_gain_scales_only_its_channel():
    r, g, b = transform(0.5, 0.5, 0.5, {**NATIVE, "gain_r": 120, "gain_b": 80})
    assert r > 0.5 and b < 0.5 and _close((g,), (0.5,))


def test_hue_leaves_gray_unchanged():
    # A hue rotation is achromatic-preserving: neutral grey stays grey.
    for v in (0.2, 0.5, 0.8):
        assert _close(transform(v, v, v, {**NATIVE, "hue": 100}), (v, v, v), tol=1e-4)


def test_hue_shifts_a_colored_pixel():
    base = transform(0.8, 0.2, 0.2, NATIVE)
    rot = transform(0.8, 0.2, 0.2, {**NATIVE, "hue": 100})
    assert not _close(rot, base, tol=1e-3)


def test_black_positive_raises_black_point_keeps_white():
    r, _, _ = transform(0.0, 0.0, 0.0, {**NATIVE, "black": 100})
    assert r > 0.0                                   # black lifted (shadow detail)
    assert _close(transform(1.0, 1.0, 1.0, {**NATIVE, "black": 100}), (1.0, 1.0, 1.0), tol=1e-6)


def test_black_negative_deepens_shadows_keeps_white():
    r, _, _ = transform(0.08, 0.08, 0.08, {**NATIVE, "black": -100})
    assert r == 0.0                                  # near-black crushed to 0
    assert _close(transform(1.0, 1.0, 1.0, {**NATIVE, "black": -100}), (1.0, 1.0, 1.0), tol=1e-6)


def test_vibrance_leaves_gray_unchanged():
    assert _close(transform(0.5, 0.5, 0.5, {**NATIVE, "vibrance": 100}), (0.5, 0.5, 0.5), tol=1e-6)


def test_vibrance_boosts_low_saturation_more_than_high():
    def spread(px, st):
        r, g, b = transform(*px, st)
        return max(r, g, b) - min(r, g, b)
    low = (0.55, 0.5, 0.45)   # barely saturated
    high = (0.95, 0.15, 0.1)  # already vivid
    low_gain = spread(low, {**NATIVE, "vibrance": 100}) - spread(low, NATIVE)
    high_gain = spread(high, {**NATIVE, "vibrance": 100}) - spread(high, NATIVE)
    assert low_gain > 0 and low_gain > high_gain


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
    def __init__(self, ok=True, info=None):
        self.ok = ok
        self.calls = []
        self.info = info or (
            "gamescope_control info:\n"
            "  - Connector Name: eDP-1\n"
            "  - Display Flags: 0x3\n"
            "  Features:\n"
            "  - Look (6) - Version: 1 - Flags: 0x0\n"
        )

    def __call__(self, args, env):
        self.calls.append((args, env))
        output = self.info if len(args) == 1 else "gamescope version 3.16"
        return (0 if self.ok else 1, output if self.ok else "")


class FakeLookAtom:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.value = None
        self.writes = []

    def write(self, session, value):
        self.writes.append((session, value))
        if self.accepted:
            self.value = value or None
        return self.accepted

    def read(self, session):
        return self.value


class FlakyLookAtom(FakeLookAtom):
    def __init__(self):
        super().__init__()
        self.readback_unavailable = False

    def read(self, session):
        if self.readback_unavailable:
            return _UNAVAILABLE_LOOK
        return super().read(session)


class SequencedLookAtom(FakeLookAtom):
    def __init__(self):
        super().__init__()
        self.next_reads = []

    def read(self, session):
        if self.next_reads:
            return self.next_reads.pop(0)
        return super().read(session)


class FailNextLookAtom(FakeLookAtom):
    def __init__(self):
        super().__init__()
        self.fail_next = False

    def write(self, session, value):
        if self.fail_next:
            self.fail_next = False
            self.writes.append((session, value))
            return False
        return super().write(session, value)


class UnconfirmedLookAtom(FailNextLookAtom):
    def write(self, session, value):
        if self.fail_next:
            self.fail_next = False
            self.writes.append((session, value))
            self.value = value or None
            return False
        return super().write(session, value)


def _backend(tmp_path, ok=True, force_composite=False, hdr_look=False,
             info=None, edid_pq=True, clock=None, pq_atom=None):
    sock = tmp_path / "run" / "user" / "1000" / "gamescope-0"
    sock.parent.mkdir(parents=True)
    sock.write_text("")
    r = FakeRunner(ok=ok, info=info)
    if hdr_look and pq_atom is None:
        pq_atom = FakeLookAtom()
    b = GamescopeColorBackend(runner=r, socket_glob=str(tmp_path / "run/user/*/gamescope-*"),
                              lut_path=str(tmp_path / "look.cube"), force_composite=force_composite,
                              hdr_look=hdr_look,
                              edid_pq=lambda _connector: edid_pq,
                              pq_atom=pq_atom,
                              socket_owner=lambda _path: 123,
                              **({"clock": clock} if clock is not None else {}))
    return b, r


def _composite_calls(runner):
    return [c[0] for c in runner.calls if c[0][:2] == ["gamescopectl", "composite_force"]]


def test_backend_supported_when_gamescopectl_responds(tmp_path):
    b, r = _backend(tmp_path)
    assert b.supported is True
    _, env = r.calls[0]
    assert env["WAYLAND_DISPLAY"] == "gamescope-0"
    assert env["GAMESCOPE_WAYLAND_DISPLAY"] == "gamescope-0"
    assert env["XDG_RUNTIME_DIR"].endswith("/1000")


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


def test_backend_discards_ownership_and_reprobes_when_session_restarts(
    tmp_path,
):
    b, r = _backend(tmp_path, hdr_look=True)
    assert b.apply({**NATIVE, "hdr_saturation": 130}) is True
    before = b.display_fingerprint()
    socket = tmp_path / "run" / "user" / "1000" / "gamescope-0"
    socket.unlink()
    socket.write_text("")
    r.calls.clear()

    after = b.display_fingerprint()

    assert after != before
    assert b.diagnostics()["managed"] is False
    assert not _unsetlooks(r)


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


def test_probe_detail_reports_missing_socket(tmp_path):
    (tmp_path / "run").mkdir()
    b = GamescopeColorBackend(runner=FakeRunner(),
                              socket_glob=str(tmp_path / "run/user/*/gamescope-*"))
    assert b.supported is False
    assert "no gamescope socket" in b.probe_detail


def test_probe_detail_reports_socket_and_rc(tmp_path):
    b, _ = _backend(tmp_path, ok=True)
    assert b.supported is True
    assert "gamescope-0" in b.probe_detail and "rc=0" in b.probe_detail


def test_probe_detail_reports_nonzero_rc(tmp_path):
    b = GamescopeColorBackend(runner=FakeRunner(ok=False),
                              socket_glob=str(tmp_path / "run/user/*/gamescope-*"),
                              lut_path=str(tmp_path / "look.cube"))
    sock = tmp_path / "run" / "user" / "1000" / "gamescope-0"
    sock.parent.mkdir(parents=True)
    sock.write_text("")
    assert b.supported is False
    assert "rc=1" in b.probe_detail


def test_backend_apply_writes_cube_and_calls_set_look(tmp_path):
    b, r = _backend(tmp_path)
    r.calls.clear()
    assert b.apply({**NATIVE, "saturation": 150}) is True
    setlook = [c for c in r.calls if c[0][:2] == ["gamescopectl", "set_look"]]
    assert len(setlook) == 1
    path = setlook[0][0][2]
    assert path.endswith("look.cube")
    assert "LUT_3D_SIZE" in open(path).read()


def test_backend_applies_g22_and_pq_looks_in_one_command(tmp_path):
    atom = FakeLookAtom()
    b, r = _backend(tmp_path, hdr_look=True, pq_atom=atom)
    r.calls.clear()

    assert b.apply({
        **NATIVE, "saturation": 130, "hdr_saturation": 140,
    }) is True

    command = _setlooks(r)[0][0]
    assert len(command) == 3
    assert "LUT_3D_SIZE 17" in open(command[2]).read()
    assert "LUT_3D_SIZE 33" in open(atom.value).read()
    assert os.stat(command[2]).st_mode & 0o004
    assert os.stat(atom.value).st_mode & 0o004


def test_backend_alternates_complete_lut_pairs_between_applies(tmp_path):
    atom = FakeLookAtom()
    b, r = _backend(tmp_path, hdr_look=True, pq_atom=atom)
    r.calls.clear()

    assert b.apply({**NATIVE, "hdr_saturation": 120}) is True
    assert b.apply({**NATIVE, "hdr_saturation": 125}) is True

    first, second = [call[0] for call in _setlooks(r)]
    pq_paths = [value for _session, value in atom.writes]
    assert first[2:] != second[2:]
    assert pq_paths[0] != pq_paths[1]
    assert all(os.path.exists(path) for path in first[2:] + second[2:] + pq_paths)


def test_backend_rejects_pq_apply_without_atom_readback(tmp_path):
    atom = FakeLookAtom(accepted=False)
    b, r = _backend(tmp_path, hdr_look=True, pq_atom=atom)

    assert b.apply({**NATIVE, "hdr_saturation": 140}) is False
    assert b.diagnostics()["last_apply"]["pq_atom"] is False
    atom.accepted = True
    r.calls.clear()
    assert b.apply(NATIVE) is True
    assert _unsetlooks(r) == []
    assert _setlooks(r) == []


def test_failed_pq_publication_restores_previous_complete_pair(tmp_path):
    atom = FailNextLookAtom()
    backend, runner = _backend(
        tmp_path, hdr_look=True, pq_atom=atom
    )
    first = {**NATIVE, "saturation": 120, "hdr_saturation": 130}
    second = {**NATIVE, "saturation": 140, "hdr_saturation": 150}

    assert backend.apply(first) is True
    previous_g22 = _setlooks(runner)[-1][0][2]
    previous_pq = atom.value
    atom.fail_next = True

    assert backend.apply(second) is False

    assert _setlooks(runner)[-1][0][2] == previous_g22
    assert atom.value == previous_pq
    assert backend.diagnostics()["last_apply"]["rollback_confirmed"] is True


def test_failed_pq_clear_restores_previous_complete_pair(tmp_path):
    atom = FailNextLookAtom()
    backend, runner = _backend(tmp_path, hdr_look=True, pq_atom=atom)
    vivid = {**NATIVE, "saturation": 120, "hdr_saturation": 130}
    assert backend.apply(vivid) is True
    previous_g22 = _setlooks(runner)[-1][0][2]
    previous_pq = atom.value
    atom.fail_next = True

    assert backend.apply(NATIVE) is False

    assert _setlooks(runner)[-1][0][2] == previous_g22
    assert atom.value == previous_pq
    assert backend.diagnostics()["last_apply"]["rollback_confirmed"] is True


def test_unconfirmed_pq_clear_republishes_previous_pair(tmp_path):
    atom = UnconfirmedLookAtom()
    backend, runner = _backend(tmp_path, hdr_look=True, pq_atom=atom)
    assert backend.apply({**NATIVE, "hdr_saturation": 130}) is True
    previous_g22 = _setlooks(runner)[-1][0][2]
    previous_pq = atom.value
    atom.fail_next = True

    assert backend.apply(NATIVE) is False

    assert _setlooks(runner)[-1][0][2] == previous_g22
    assert atom.value == previous_pq
    assert backend.diagnostics()["last_apply"]["rollback_confirmed"] is True


def test_backend_does_not_replace_a_foreign_pq_atom(tmp_path):
    atom = FakeLookAtom()
    atom.value = "/tmp/another-plugin.cube"
    b, r = _backend(tmp_path, hdr_look=True, pq_atom=atom)
    r.calls.clear()

    assert b.apply({**NATIVE, "hdr_saturation": 140}) is False
    assert atom.value == "/tmp/another-plugin.cube"
    assert _setlooks(r) == []
    assert b.diagnostics()["last_apply"]["reason"] == "pq_atom_conflict"


def test_display_fingerprint_detects_dropped_owned_pq_atom(tmp_path):
    atom = FakeLookAtom()
    b, _ = _backend(tmp_path, hdr_look=True, pq_atom=atom)
    assert b.apply({**NATIVE, "hdr_saturation": 140}) is True
    before = b.display_fingerprint()

    atom.value = None

    assert b.display_fingerprint() != before


def test_display_fingerprint_observes_pending_pq_release_on_external(
    tmp_path,
):
    atom = FlakyLookAtom()
    backend, runner = _backend(tmp_path, hdr_look=True, pq_atom=atom)
    assert backend.apply({**NATIVE, "hdr_saturation": 140}) is True
    runner.info = (
        "gamescope_control info:\n"
        "  - Connector Name: DP-1\n"
        "  - Display Flags: 0x2\n"
        "  Features:\n"
        "  - Look (6) - Version: 1 - Flags: 0x0\n"
    )
    atom.readback_unavailable = True
    unavailable = backend.display_fingerprint()
    atom.readback_unavailable = False

    assert backend.display_fingerprint() != unavailable


def test_display_fingerprint_detects_cleared_foreign_pq_conflict(tmp_path):
    atom = FakeLookAtom()
    atom.value = "/tmp/another-plugin.cube"
    backend, _ = _backend(tmp_path, hdr_look=True, pq_atom=atom)

    conflict = backend.display_fingerprint()
    atom.value = None

    assert backend.display_fingerprint() != conflict


def test_backend_does_not_clear_a_foreign_pq_replacement_on_release(tmp_path):
    atom = FakeLookAtom()
    b, r = _backend(tmp_path, hdr_look=True, pq_atom=atom)
    assert b.apply({**NATIVE, "hdr_saturation": 140}) is True
    r.calls.clear()
    atom.value = "/tmp/another-plugin.cube"

    assert b.apply(NATIVE) is True
    assert atom.value == "/tmp/another-plugin.cube"
    assert _unsetlooks(r) == []
    assert len(_setlooks(r)) == 1
    assert b.diagnostics()["last_apply"]["reason"] == (
        "pq_atom_ownership_lost"
    )
    assert b.diagnostics()["managed"] is False


def test_backend_retries_release_after_transient_pq_readback_failure(tmp_path):
    atom = FlakyLookAtom()
    b, _ = _backend(tmp_path, hdr_look=True, pq_atom=atom)
    assert b.apply({**NATIVE, "hdr_saturation": 140}) is True
    atom.readback_unavailable = True

    assert b.apply(NATIVE) is False
    assert b.diagnostics()["managed_pq_atom"] is True
    assert b.diagnostics()["last_apply"]["reason"] == (
        "pq_atom_readback_unavailable"
    )

    atom.readback_unavailable = False
    assert b.apply(NATIVE) is True
    assert atom.value is None
    assert b.diagnostics()["managed_pq_atom"] is False


def test_backend_uses_one_pq_observation_during_release(tmp_path):
    atom = SequencedLookAtom()
    b, _ = _backend(tmp_path, hdr_look=True, pq_atom=atom)
    assert b.apply({**NATIVE, "hdr_saturation": 140}) is True
    atom.next_reads = [atom.value, _UNAVAILABLE_LOOK]

    assert b.apply(NATIVE) is True
    assert atom.next_reads == [_UNAVAILABLE_LOOK]
    assert atom.value is None


def test_backend_keeps_legacy_g22_command_when_hdr_look_not_requested(tmp_path):
    b, r = _backend(tmp_path, hdr_look=False)
    r.calls.clear()

    assert b.apply({**NATIVE, "saturation": 130}) is True

    assert _setlooks(r)[0][0] == [
        "gamescopectl", "set_look", str(tmp_path / "look.cube"),
    ]


def test_backend_falls_back_to_g22_when_look_feature_is_missing(tmp_path):
    info = (
        "gamescope_control info:\n"
        "  - Connector Name: eDP-1\n"
        "  - Display Flags: 0x3\n"
        "  Features:\n"
    )
    b, r = _backend(tmp_path, hdr_look=True, info=info)
    r.calls.clear()

    assert b.hdr_look_supported is False
    assert b.apply({**NATIVE, "saturation": 130}) is True
    assert len(_setlooks(r)[0][0]) == 3


def test_backend_recognizes_look_feature_when_client_label_is_stale(tmp_path):
    info = (
        "gamescope_control info:\n"
        "  - Connector Name: eDP-1\n"
        "  - Display Flags: 0x7\n"
        "  Features:\n"
        "  - Unknown (6) - Version: 1 - Flags: 0x0\n"
    )
    b, _ = _backend(tmp_path, hdr_look=True, info=info)

    assert b.hdr_look_supported is True
    assert "look=1" in b.diagnostics()["hdr_look_detail"]


def test_backend_rejects_hdr_look_on_external_connector(tmp_path):
    info = (
        "gamescope_control info:\n"
        "  - Connector Name: DP-1\n"
        "  - Display Flags: 0x3\n"
        "  Features:\n"
        "  - Look (6) - Version: 1 - Flags: 0x0\n"
    )

    backend, _ = _backend(tmp_path, hdr_look=True, info=info)

    assert backend.hdr_look_supported is False
    assert "internal_connector=False" in backend.diagnostics()["hdr_look_detail"]


def test_backend_falls_back_to_g22_when_active_panel_edid_has_no_pq(tmp_path):
    b, r = _backend(tmp_path, hdr_look=True, edid_pq=False)
    r.calls.clear()

    assert b.hdr_look_supported is False
    assert b.apply({**NATIVE, "saturation": 130, "hdr_saturation": 140}) is True
    assert len(_setlooks(r)[0][0]) == 3
    assert "edid_pq=False" in b.diagnostics()["hdr_look_detail"]


def test_backend_rechecks_active_display_before_applying_hdr_pair(tmp_path):
    b, r = _backend(tmp_path, hdr_look=True)
    assert b.apply({**NATIVE, "hdr_saturation": 140}) is True
    r.calls.clear()
    r.info = (
        "gamescope_control info:\n"
        "  - Connector Name: DP-1\n"
        "  - Display Flags: 0x2\n"
        "  Features:\n"
        "  - Look (6) - Version: 1 - Flags: 0x0\n"
    )

    assert b.apply({**NATIVE, "saturation": 130, "hdr_saturation": 140}) is True
    assert b.hdr_look_supported is False
    assert len(_setlooks(r)[0][0]) == 3
    assert len(_unsetlooks(r)) == 0


def test_backend_diagnostics_report_successful_set_look(tmp_path):
    b, _ = _backend(tmp_path)

    assert b.apply({**NATIVE, "saturation": 150}) is True

    diagnostics = getattr(b, "diagnostics", lambda: None)()
    assert diagnostics is not None
    assert diagnostics["supported"] is True
    assert diagnostics["wayland_display"] == "gamescope-0"
    assert diagnostics["last_apply"] == {
        "operation": "set_look",
        "ok": True,
        "rc": 0,
    }
    assert diagnostics["managed"] is True
    assert diagnostics["look_paths"]["g22"].endswith("look.cube")
    assert diagnostics["desired"]["saturation"] == 150
    assert "version rc=0" in diagnostics["probe_detail"]


def test_backend_diagnostics_report_failed_set_look(tmp_path):
    b, runner = _backend(tmp_path)
    runner.ok = False

    assert b.apply({**NATIVE, "saturation": 150}) is False

    diagnostics = getattr(b, "diagnostics", lambda: None)()
    assert diagnostics is not None
    assert diagnostics["last_apply"] == {
        "operation": "set_look",
        "ok": False,
        "rc": 1,
    }


def test_backend_invalidates_failed_session_and_reprobes_on_next_apply(tmp_path):
    now = [100.0]
    b, runner = _backend(tmp_path, clock=lambda: now[0])
    runner.ok = False

    assert b.apply({**NATIVE, "saturation": 150}) is False
    assert b.supported is False

    runner.ok = True
    now[0] += _PROBE_RETRY_S + 1
    assert b.apply({**NATIVE, "saturation": 150}) is True


def _setlooks(runner):
    return [c for c in runner.calls if c[0][:2] == ["gamescopectl", "set_look"]]


def _unsetlooks(runner):
    return [c for c in runner.calls if c[0][:2] == ["gamescopectl", "unset_look"]]


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


def test_backend_rolls_back_composition_when_set_look_fails(tmp_path):
    b, r = _backend(tmp_path, force_composite=True)
    original = r.__call__

    def fail_set_look(args, env):
        if args[:2] == ["gamescopectl", "set_look"]:
            r.calls.append((args, env))
            return 1, ""
        return original(args, env)

    b._run = fail_set_look
    r.calls.clear()

    assert b.apply({**NATIVE, "saturation": 150}) is False
    assert _composite_calls(r) == [
        ["gamescopectl", "composite_force", "1"],
        ["gamescopectl", "composite_force", "0"],
    ]
    assert b.diagnostics()["composite_managed"] is False


def test_backend_retries_composition_release_without_unsetting_twice(tmp_path):
    b, r = _backend(tmp_path, force_composite=True)
    assert b.apply({**NATIVE, "saturation": 150}) is True
    original = r.__call__

    def fail_composite_off(args, env):
        if args == ["gamescopectl", "composite_force", "0"]:
            r.calls.append((args, env))
            return 1, ""
        return original(args, env)

    b._run = fail_composite_off
    r.calls.clear()

    assert b.release() is False
    assert len(_unsetlooks(r)) == 1
    assert b.diagnostics()["managed"] is False
    assert b.diagnostics()["composite_managed"] is True

    b._run = original
    r.calls.clear()
    assert b.release() is True
    assert _unsetlooks(r) == []
    assert _composite_calls(r) == [
        ["gamescopectl", "composite_force", "0"],
    ]


def test_backend_does_not_touch_an_unowned_look_for_native_state(tmp_path):
    b, r = _backend(tmp_path)
    r.calls.clear()
    assert b.apply(NATIVE) is True
    assert _setlooks(r) == []
    assert _unsetlooks(r) == []


def test_backend_clears_look_once_when_returning_to_native(tmp_path):
    b, r = _backend(tmp_path)
    b.apply({**NATIVE, "saturation": 150})  # non-native → loaded
    r.calls.clear()
    assert b.apply(NATIVE) is True          # returns to native → clears once
    assert len(_unsetlooks(r)) == 1
    r.calls.clear()
    assert b.apply(NATIVE) is True          # already native → skipped
    assert _unsetlooks(r) == []


def test_backend_release_only_unsets_a_look_owned_by_this_instance(tmp_path):
    b, r = _backend(tmp_path)
    r.calls.clear()
    assert b.release() is True
    assert _unsetlooks(r) == []

    assert b.apply({**NATIVE, "saturation": 150}) is True
    r.calls.clear()
    assert b.release() is True
    assert len(_unsetlooks(r)) == 1
