from types import SimpleNamespace

import pytest

from tdp import diagnostics
from tdp.types import RailReading, TdpObservation


class Backend:
    name = "test"

    def __init__(self):
        self.watts = 15
        self.reads = 0

    def observe(self):
        self.reads += 1
        return TdpObservation(True, {"hardware": {"pl1": RailReading(self.watts, 3, 30)}})


@pytest.fixture
def events(monkeypatch):
    events = []
    monkeypatch.setattr(diagnostics.journal, "active", SimpleNamespace(write=lambda *a, **kw: events.append((a, kw))))
    return events


def test_operation_records_real_readback_and_bounded_fields(events):
    backend = Backend()
    with diagnostics.trace_operation(backend, "set", observation_before=backend.observe().as_dict(), target={"pl1": 20, "secret": "x" * 10000}, on_ac=True) as trace:
        backend.watts = 20
        trace["result"] = {"ok": True, "applied_w": 20, "detail": "private data"}
    args, event = events[0]
    assert args == ("INFO", "tdp", "backend_operation")
    assert event["before_cached"]["surfaces"]["hardware"]["pl1"]["applied"] == 15
    assert "after" not in event
    assert event["target"] == {"pl1": 20}
    assert event["result"] == {"ok": True, "applied_w": 20}


def test_no_journal_does_not_probe(monkeypatch):
    monkeypatch.setattr(diagnostics.journal, "active", None)
    backend = Backend()
    with diagnostics.trace_operation(backend, "set"):
        backend.watts = 20
    assert backend.reads == 0
    assert backend.watts == 20


def test_no_hardware_probes_even_with_journal(events):
    backend = Backend()
    backend.observe = lambda: (_ for _ in ()).throw(AssertionError("unexpected hardware probe"))
    backend.read_profile = backend.observe
    backend.diagnostics = backend.observe
    result = diagnostics.run_operation(backend, "set", lambda: {"ok": False})
    assert result == {"ok": False}
    assert events[0][1]["before_cached"] == {"readable": None, "surfaces": {}}


def test_journal_failure_preserves_body_and_original_exception(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("journal failure")
    monkeypatch.setattr(diagnostics.journal, "active", SimpleNamespace(write=fail))
    backend = Backend()
    with diagnostics.trace_operation(backend, "set"):
        backend.watts = 20
    original = ValueError("body failure")
    with pytest.raises(ValueError) as captured:
        with diagnostics.trace_operation(backend, "set"):
            raise original
    assert captured.value is original
    assert backend.watts == 20


def test_exception_is_warning_without_message(events):
    with pytest.raises(ValueError):
        with diagnostics.trace_operation(Backend(), "set"):
            raise ValueError("private data")
    assert events[0][0][0] == "WARNING"
    assert events[0][1]["result"]["exception"] == {"type": "ValueError", "errno": None}


def test_success_duplicates_suppressed_but_failures_retained(events):
    backend = Backend()
    for ok in (True, True, False, False):
        with diagnostics.trace_operation(backend, "set") as trace:
            trace["result"] = {"ok": ok}
    assert [args[0] for args, _ in events] == ["INFO", "WARNING", "WARNING"]


def test_run_operation_preserves_exact_result_and_observed_unknown(events):
    from tdp.types import TdpResult
    result = TdpResult(15, None, False, "private details", "unreadable")
    assert diagnostics.run_operation(Backend(), "set", lambda: result) is result
    assert events[0][1]["result"]["applied_w"] is None
    assert "detail" not in events[0][1]["result"]


def test_cached_snapshot_is_bounded(events):
    observation = {"readable": True, "surfaces": {str(i): {str(j): {"applied": None, "private": "secret"} for j in range(20)} for i in range(20)}}
    diagnostics.run_operation(
        Backend(), "set", lambda: True, observation_before=observation,
    )
    cached = events[0][1]["before_cached"]
    assert len(cached["surfaces"]) == 4
    assert all(len(rails) == 4 for rails in cached["surfaces"].values())
    assert "secret" not in str(cached)


def test_success_dedupe_expires_and_does_not_hide_changed_requests(events, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(diagnostics.time, "monotonic", lambda: now[0])
    backend = Backend()
    for watts, elapsed in ((15, 0), (15, 30), (15, 61), (20, 62)):
        now[0] = 100.0 + elapsed
        diagnostics.run_operation(backend, "set", lambda: True, target={"watts": watts})
    assert [event["target"]["watts"] for _, event in events] == [15, 15, 20]


def test_raw_target_cannot_expand_event(events):
    diagnostics.run_operation(Backend(), "set", lambda: True, target="x" * 10000)
    assert len(events[0][1]["target"]) == 128


def test_operation_survives_collection_into_older_report(tmp_path, monkeypatch):
    import journal
    now = 1790000000.0
    diary = journal.Journal(str(tmp_path), clock=lambda: now)
    monkeypatch.setattr(journal, "active", diary)
    diary.start()
    try:
        diagnostics.run_operation(Backend(), "recover", lambda: {"ok": False})
    finally:
        diary.stop()
    bundle = journal.collect(str(tmp_path), now=now + 2 * 86400)
    event = next(row for row in bundle["older"] if row["m"] == "backend_operation")
    assert event["operation"] == "recover"
    assert event["result"]["ok"] is False


def test_recovery_after_failure_is_not_deduplicated(events):
    backend = Backend()
    for ok in (True, False, True):
        diagnostics.run_operation(backend, "recover", lambda: ok)
    assert [event["result"]["ok"] for _, event in events] == [True, False, True]
