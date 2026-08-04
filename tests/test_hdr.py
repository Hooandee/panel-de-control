import os

from display.hdr import (
    GamescopeLookAtom,
    HdrBackend,
    _MIXED_LOOK,
    _UNAVAILABLE_LOOK,
    _read_hdr_feedback,
    _select_feedback,
)


class _Runner:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        return (0 if self.ok else 1, "")


class _Feedback:
    def __init__(self, *values):
        self.values = list(values)

    def __call__(self, _session=None):
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0] if self.values else None


def test_backend_toggles_hdr():
    r = _Runner()
    b = HdrBackend(
        r,
        feedback_reader=_Feedback(False, True, True, False),
        sleep=lambda _: None,
    )
    assert b.set_enabled(True) is True
    assert r.calls[:2] == [["hdr_enabled", "1"], ["debug_force_repaint"]]
    b.set_enabled(False)
    assert r.calls[-2:] == [["hdr_enabled", "0"], ["debug_force_repaint"]]
    assert b.diagnostics()["actual_enabled"] is False
    assert b.diagnostics()["readback"] is True


def test_backend_reports_failure():
    backend = HdrBackend(_Runner(ok=False))

    assert backend.set_enabled(True) is False
    assert backend.diagnostics() == {
        "enabled": True, "ok": False, "rc": 1,
    }


def test_backend_does_not_claim_hdr_when_feedback_never_matches():
    backend = HdrBackend(
        _Runner(),
        feedback_reader=_Feedback(False),
        sleep=lambda _: None,
        readback_attempts=3,
    )

    assert backend.set_enabled(True) is False
    assert backend.diagnostics() == {
        "enabled": True,
        "actual_enabled": False,
        "ok": False,
        "rc": 0,
        "readback": True,
        "reason": "feedback_mismatch",
    }


def test_backend_keeps_command_acceptance_distinct_without_feedback():
    backend = HdrBackend(
        _Runner(), feedback_reader=_Feedback(None), sleep=lambda _: None,
    )

    assert backend.set_enabled(True) is True
    assert backend.diagnostics() == {
        "enabled": True,
        "actual_enabled": None,
        "ok": True,
        "rc": 0,
        "readback": False,
        "confirmation": "accepted",
    }


def test_feedback_rejects_mixed_gamescope_instances():
    assert _select_feedback([(100, True), (100, True)]) is True
    assert _select_feedback([(100, True), (101, True)]) is None
    assert _select_feedback([(100, True), (100, False)]) is None


def test_feedback_is_limited_to_the_target_runtime_user():
    calls = []
    uid = os.getuid()
    runtime = f"/run/user/{uid}"

    def read_root(uid, username, runtime_dir, display):
        calls.append((uid, username, runtime_dir, display))
        return "\n".join((
            "GAMESCOPE_PID(CARDINAL) = 123",
            "GAMESCOPE_HDR_OUTPUT_FEEDBACK(CARDINAL) = 1",
        ))

    value = _read_hdr_feedback(
        (runtime, "gamescope-0", (1, 2, 123)),
        read_root=read_root,
        displays=lambda: [":0", ":1"],
    )

    assert value is True
    assert calls == [
        (uid, calls[0][1], runtime, ":0"),
        (uid, calls[0][1], runtime, ":1"),
    ]


def test_backend_rejects_a_gamescope_session_change():
    sessions = iter((
        ("/run/user/1000", "gamescope-0", (1, 2)),
        ("/run/user/1000", "gamescope-0", (1, 3)),
    ))
    backend = HdrBackend(
        _Runner(),
        feedback_reader=_Feedback(True),
        session_provider=lambda: next(sessions),
    )

    assert backend.set_enabled(True) is False
    assert backend.diagnostics()["reason"] == "session_changed"
    assert backend.diagnostics()["session_identity"] == (1, 2)


def test_backend_records_the_confirmed_gamescope_session():
    session = ("/run/user/1000", "gamescope-0", (1, 2))
    backend = HdrBackend(
        _Runner(),
        feedback_reader=_Feedback(True),
        session_provider=lambda: session,
    )

    assert backend.set_enabled(True) is True
    assert backend.diagnostics()["session_identity"] == (1, 2)


def test_look_atom_writes_and_reads_back_the_selected_xwayland():
    uid = os.getuid()
    runtime = f"/run/user/{uid}"
    values = {}

    def read_root(_uid, _username, _runtime, display, atom):
        value = values.get(display)
        atom_line = (
            f'{atom}(UTF8_STRING) = "{value}"'
            if value is not None else f"{atom}:  no such atom"
        )
        return f"GAMESCOPE_PID(CARDINAL) = 123\n{atom_line}"

    def write_root(_uid, _username, _runtime, display, _atom, value):
        values[display] = value
        return True

    atom = GamescopeLookAtom(
        read_root=read_root,
        write_root=write_root,
        displays=lambda: [":0", ":1"],
    )
    session = (runtime, "gamescope-0", (1, 2, 123))

    assert atom.write(session, "/tmp/look.pq.cube") is True
    assert atom.read(session) == "/tmp/look.pq.cube"
    assert values == {":0": "/tmp/look.pq.cube"}


def test_look_atom_detects_a_foreign_value_on_the_second_xwayland():
    uid = os.getuid()
    runtime = f"/run/user/{uid}"
    values = {
        ":0": "/tmp/pdc.cube",
        ":1": "/tmp/another-plugin.cube",
    }

    def read_root(_uid, _username, _runtime, display, atom):
        return "\n".join((
            "GAMESCOPE_PID(CARDINAL) = 123",
            f'{atom}(UTF8_STRING) = "{values[display]}"',
        ))

    atom = GamescopeLookAtom(
        read_root=read_root,
        write_root=lambda *_args: True,
        displays=lambda: [":0", ":1"],
    )

    assert atom.read((runtime, "gamescope-0", (1, 2, 123))) == _MIXED_LOOK


def test_look_atom_distinguishes_unavailable_readback_from_empty_atom():
    uid = os.getuid()
    runtime = f"/run/user/{uid}"
    atom = GamescopeLookAtom(
        read_root=lambda *_args: None,
        write_root=lambda *_args: True,
        displays=lambda: [":0"],
    )

    assert atom.read(
        (runtime, "gamescope-0", (1, 2, 123))
    ) == _UNAVAILABLE_LOOK


def test_xwayland_observations_must_match_wayland_socket_owner():
    uid = os.getuid()
    runtime = f"/run/user/{uid}"

    def read_root(_uid, _username, _runtime, _display, atom):
        return "\n".join((
            "GAMESCOPE_PID(CARDINAL) = 100",
            f'{atom}(UTF8_STRING) = "/tmp/foreign.cube"',
        ))

    atom = GamescopeLookAtom(
        read_root=read_root,
        write_root=lambda *_args: True,
        displays=lambda: [":0"],
    )
    session = (runtime, "gamescope-0", (1, 2, 200))

    assert atom.read(session) == _UNAVAILABLE_LOOK
    assert atom.write(session, "/tmp/ours.cube") is False
    assert _read_hdr_feedback(
        session,
        read_root=lambda *_args: "\n".join((
            "GAMESCOPE_PID(CARDINAL) = 100",
            "GAMESCOPE_HDR_OUTPUT_FEEDBACK(CARDINAL) = 1",
        )),
        displays=lambda: [":0"],
    ) is None
