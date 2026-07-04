"""Steam Deck software-loop fan backend (steamdeck_hwmon: fan1_target RPM +
re-assert). Synthetic sysfs; the asyncio loop itself isn't exercised — the
testable seams are target_for_temp (pure), the immediate apply, and release."""
import os

from fans.software_loop import SteamDeckFanBackend
from fans.control import select_fan_backend, NullFanBackend


def _w(d, name, val):
    with open(os.path.join(d, name), "w") as f:
        f.write(str(val))


def _r(d, name):
    with open(os.path.join(d, name)) as f:
        return f.read().strip()


def _make_deck_chip(root, idx=0, board="Jupiter"):
    d = os.path.join(root, "sys/class/hwmon", f"hwmon{idx}")
    os.makedirs(d, exist_ok=True)
    _w(d, "name", "steamdeck_hwmon")
    _w(d, "fan1_input", "1500")
    _w(d, "fan1_target", "1500")
    return d


CURVE = [(40, 0), (50, 30), (60, 60), (70, 95), (80, 135), (85, 175), (90, 215), (95, 255)]


def _backend(root, temp=70.0):
    # Inject an always-succeeds jupiter controller so driving works off-device
    # (tests run on machines without systemctl / jupiter-fan-control).
    return SteamDeckFanBackend(root=str(root), temp_fn=lambda: temp,
                               jupiter_ctl=lambda _verb: True)


class TestSteamDeckBackend:
    def test_supported_when_chip_present(self, tmp_path):
        _make_deck_chip(str(tmp_path))
        assert _backend(tmp_path).supported is True

    def test_unsupported_without_chip(self, tmp_path):
        assert _backend(tmp_path).supported is False

    def test_read_state_reports_source(self, tmp_path):
        _make_deck_chip(str(tmp_path))
        st = _backend(tmp_path).read_state()
        assert st["supported"] is True
        assert st["source"] == "steamdeck_hwmon"

    def test_target_for_temp_monotonic_and_in_rpm_range(self, tmp_path):
        _make_deck_chip(str(tmp_path))
        b = _backend(tmp_path)
        b.apply_curve_all(CURVE)
        lo, hi = b.target_for_temp(45), b.target_for_temp(90)
        assert 0 <= lo <= hi <= b.max_rpm
        assert hi > lo

    def test_apply_writes_positive_target_and_switches_to_manual(self, tmp_path):
        d = _make_deck_chip(str(tmp_path))
        b = _backend(tmp_path, temp=85.0)
        res = b.apply_curve_all(CURVE)
        assert res["ok"] is True
        assert int(_r(d, "fan1_target")) == b.target_for_temp(85.0)
        assert int(_r(d, "fan1_target")) > 0

    def test_zero_duty_curve_does_not_write_release_sentinel(self, tmp_path):
        # A curve with 0% duty at cool temps must still DRIVE (>=1), never write 0 —
        # 0 means "release to firmware", which would silently drop manual control.
        d = _make_deck_chip(str(tmp_path))
        b = _backend(tmp_path, temp=40.0)  # 40C → CURVE duty 0
        b.apply_curve_all(CURVE)
        assert b.target_for_temp(40.0) >= 1
        assert int(_r(d, "fan1_target")) >= 1

    def test_set_auto_releases_to_firmware_with_zero(self, tmp_path):
        d = _make_deck_chip(str(tmp_path))
        b = _backend(tmp_path)
        b.apply_curve_all(CURVE)
        b.set_auto(None)
        assert int(_r(d, "fan1_target")) == 0

    def test_factory_selects_deck(self, tmp_path):
        _make_deck_chip(str(tmp_path))
        backend = select_fan_backend(None, root=str(tmp_path), temp_fn=lambda: 60.0)
        assert isinstance(backend, SteamDeckFanBackend)

    def test_factory_null_without_any_chip(self, tmp_path):
        assert isinstance(select_fan_backend(None, root=str(tmp_path)), NullFanBackend)


class _FakeSystemctl:
    """Records systemctl verb calls; returns success unless a verb is in `fail`."""

    def __init__(self, fail=()):
        self.calls: list[str] = []
        self.fail = set(fail)
        self.active = True  # jupiter-fan-control starts running (SteamOS default)

    def __call__(self, verb: str) -> bool:
        self.calls.append(verb)
        if verb in self.fail:
            return False
        if verb == "stop":
            self.active = False
        elif verb in ("start", "restart"):
            self.active = True
        return True


def _backend_svc(root, temp=70.0, svc=None):
    return SteamDeckFanBackend(root=str(root), temp_fn=lambda: temp, jupiter_ctl=svc)


class TestJupiterHandoff:
    """SteamOS's jupiter-fan-control.service continuously reclaims fan1_target,
    so we must STOP it while driving and RESTART it on release / fail-safe."""

    def test_apply_stops_jupiter_fan_control(self, tmp_path):
        _make_deck_chip(str(tmp_path))
        svc = _FakeSystemctl()
        b = _backend_svc(tmp_path, temp=85.0, svc=svc)
        res = b.apply_curve_all(CURVE)
        assert res["ok"] is True
        assert "stop" in svc.calls
        assert svc.active is False  # we own the fan now

    def test_apply_is_idempotent_stops_once(self, tmp_path):
        _make_deck_chip(str(tmp_path))
        svc = _FakeSystemctl()
        b = _backend_svc(tmp_path, temp=85.0, svc=svc)
        b.apply_curve_all(CURVE)
        b.apply_curve_all(CURVE)  # second apply must NOT re-stop
        assert svc.calls.count("stop") == 1

    def test_set_auto_restarts_jupiter_fan_control(self, tmp_path):
        _make_deck_chip(str(tmp_path))
        svc = _FakeSystemctl()
        b = _backend_svc(tmp_path, temp=85.0, svc=svc)
        b.apply_curve_all(CURVE)
        b.set_auto(None)
        assert "start" in svc.calls or "restart" in svc.calls
        assert svc.active is True  # SteamOS resumes control

    def test_release_keeps_stopped_flag_when_restart_fails(self, tmp_path):
        # if the jupiter restart FAILS on release, jupiter is still
        # down — don't clear _jupiter_stopped (that would claim it's back up).
        _make_deck_chip(str(tmp_path))
        svc = _FakeSystemctl(fail={"start"})
        b = _backend_svc(tmp_path, temp=85.0, svc=svc)
        b.apply_curve_all(CURVE)
        assert b._jupiter_stopped is True
        b.set_auto(None)  # release attempts start, which fails
        assert "start" in svc.calls
        assert svc.active is False  # jupiter genuinely still down
        assert b._jupiter_stopped is True  # flag honest, not cleared blindly

    def test_release_when_never_driving_starts_jupiter_defensively(self, tmp_path):
        # restore_auto with no prior drive should still leave jupiter running
        # (fail-safe: never leave it stopped).
        _make_deck_chip(str(tmp_path))
        svc = _FakeSystemctl()
        b = _backend_svc(tmp_path, temp=85.0, svc=svc)
        b.restore_auto()
        assert svc.active is True

    def test_no_false_manual_when_stop_fails(self, tmp_path):
        # If we cannot stop jupiter, we do NOT own the fan → don't claim to drive.
        d = _make_deck_chip(str(tmp_path))
        svc = _FakeSystemctl(fail={"stop"})
        b = _backend_svc(tmp_path, temp=85.0, svc=svc)
        before = int(_r(d, "fan1_target"))
        res = b.apply_curve_all(CURVE)
        assert res["ok"] is False
        # And we must not have written a manual target while jupiter still owns it.
        assert int(_r(d, "fan1_target")) == before

    def test_read_state_reflects_auto_when_stop_failed(self, tmp_path):
        _make_deck_chip(str(tmp_path))
        svc = _FakeSystemctl(fail={"stop"})
        b = _backend_svc(tmp_path, temp=85.0, svc=svc)
        b.apply_curve_all(CURVE)
        # enable must report firmware auto (2), not manual (1)
        assert b.read_state()["fans"][0]["enable"] == 2

    def test_guarded_never_raises_on_service_error(self, tmp_path):
        _make_deck_chip(str(tmp_path))

        def boom(_verb):
            raise RuntimeError("systemctl exploded")

        b = _backend_svc(tmp_path, temp=85.0, svc=boom)
        # apply must not raise even if the service manager throws
        res = b.apply_curve_all(CURVE)
        assert res["ok"] is False  # couldn't confirm we own the fan
        b.set_auto(None)  # must not raise

    def test_repeated_apply_then_auto_churns_jupiter_once_each(self, tmp_path):
        # A user sweeping the curve fires apply repeatedly; jupiter must be stopped
        # ONCE, then started ONCE on release — not toggled per tweak (systemd
        # rate-limits jupiter starts; excessive churn strands it dead).
        _make_deck_chip(str(tmp_path))
        svc = _FakeSystemctl()
        b = _backend_svc(tmp_path, temp=85.0, svc=svc)
        for _ in range(5):
            b.apply_curve_all(CURVE)
        b.set_auto(None)
        assert svc.calls.count("stop") == 1
        assert svc.calls.count("start") == 1


class TestJupiterStartLimit:
    """jupiter-fan-control has a systemd start rate-limit; if we trip it, systemd
    refuses to start it and the fan is left uncontrolled. The real _systemctl must
    reset-failed before every start so jupiter can ALWAYS be brought back."""

    def test_start_resets_failed_first(self, monkeypatch):
        from fans import software_loop as sl

        seen: list[list[str]] = []

        class _R:
            returncode = 0

        def fake_run(argv, **kw):
            seen.append(argv)
            return _R()

        import subprocess
        monkeypatch.setattr(subprocess, "run", fake_run)
        assert sl._systemctl("start") is True
        # reset-failed MUST precede start (clears the start-limit counter).
        verbs = [a[1] for a in seen]
        assert verbs == ["reset-failed", "start"]
        assert all(a[2] == sl._JUPITER_SERVICE for a in seen)

    def test_stop_does_not_reset_failed(self, monkeypatch):
        from fans import software_loop as sl

        seen: list[list[str]] = []

        class _R:
            returncode = 0

        import subprocess
        monkeypatch.setattr(subprocess, "run", lambda argv, **kw: (seen.append(argv), _R())[1])
        sl._systemctl("stop")
        assert [a[1] for a in seen] == ["stop"]  # no reset-failed on stop

    def test_uses_absolute_systemctl_path(self, monkeypatch):
        # The plugin runs under PyInstaller with an EMPTY PATH, so a bare
        # "systemctl" raises FileNotFoundError and jupiter is never stopped
        # (the real "curve doesn't drive at startup" bug). Must invoke by
        # absolute path.
        from fans import software_loop as sl

        seen: list[list[str]] = []

        class _R:
            returncode = 0

        import subprocess
        # Simulate SteamOS where /usr/bin/systemctl exists (the dev host may not
        # have it — the point is we resolve to the absolute path when present).
        monkeypatch.setattr(os.path, "exists", lambda p: p == "/usr/bin/systemctl")
        monkeypatch.setattr(subprocess, "run", lambda argv, **kw: (seen.append(argv), _R())[1])
        sl._systemctl("stop")
        exe = seen[0][0]
        assert os.path.isabs(exe), f"systemctl must be an absolute path, got {exe!r}"
        assert exe.endswith("systemctl")

    def test_path_prefers_existing_absolute_location(self, monkeypatch):
        from fans import software_loop as sl

        monkeypatch.setattr(os.path, "exists", lambda p: p == "/usr/bin/systemctl")
        assert sl._systemctl_path() == "/usr/bin/systemctl"

    def test_spawns_with_clean_env_not_bundle_ld_library_path(self, monkeypatch):
        # The frozen loader poisons LD_LIBRARY_PATH with its _MEI bundle (old
        # libcrypto) → systemctl fails with OPENSSL_x-not-found and jupiter never
        # stops. Must spawn with clean_env (bundle LD_LIBRARY_PATH dropped).
        from fans import software_loop as sl

        seen_env = {}

        class _R:
            returncode = 0

        def fake_run(argv, **kw):
            seen_env.update(kw.get("env") or {})
            return _R()

        import subprocess
        monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEIbundle")
        monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
        monkeypatch.setattr(subprocess, "run", fake_run)
        sl._systemctl("stop")
        # clean_env drops the bundle LD_LIBRARY_PATH (no _ORIG to restore) and
        # guarantees a usable PATH.
        assert seen_env.get("LD_LIBRARY_PATH") != "/tmp/_MEIbundle"
        assert "LD_LIBRARY_PATH" not in seen_env
        assert seen_env.get("PATH")
