import os

from display.hdr import HdrBackend, _read_hdr_feedback, _select_feedback


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
        (runtime, "gamescope-0", (1, 2)),
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
