import threading

import pytest

from mangohud.coordinator import HudClosed, HudCoordinator, HudStale


def test_refreshes_keep_only_the_active_and_latest_pending_job():
    coordinator = HudCoordinator(generation=7)
    started = threading.Event()
    release = threading.Event()
    executed = []

    def first():
        executed.append(0)
        started.set()
        release.wait(timeout=2)
        return 0

    futures = [coordinator.submit_latest(7, first)]
    assert started.wait(timeout=1)
    for value in range(1, 10):
        futures.append(
            coordinator.submit_latest(
                7,
                lambda value=value: executed.append(value) or value,
            )
        )

    release.set()

    assert futures[0].result(timeout=1) == 0
    assert futures[-1].result(timeout=1) == 9
    assert executed == [0, 9]
    assert all(future.cancelled() for future in futures[1:-1])
    coordinator.close(8, lambda: None)


def test_user_mutations_are_fifo_and_never_replaced():
    coordinator = HudCoordinator(generation=3)
    executed = []
    futures = [
        coordinator.call(
            3,
            lambda value=value: executed.append(value) or value,
        )
        for value in range(5)
    ]

    assert [future.result(timeout=1) for future in futures] == list(range(5))
    assert executed == list(range(5))
    coordinator.close(4, lambda: None)


def test_generation_mismatch_never_executes_callable():
    coordinator = HudCoordinator(generation=2)
    executed = []

    future = coordinator.call(1, lambda: executed.append(True))

    with pytest.raises(HudStale):
        future.result(timeout=1)
    assert executed == []
    coordinator.close(3, lambda: None)


def test_close_cancels_pending_waits_for_active_then_restores_once():
    coordinator = HudCoordinator(generation=0)
    started = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    events = []

    def active():
        events.append("active")
        started.set()
        release.wait(timeout=2)

    active_future = coordinator.call(0, active)
    assert started.wait(timeout=1)
    pending_refresh = coordinator.submit_latest(0, lambda: events.append("refresh"))
    pending_call = coordinator.call(0, lambda: events.append("call"))

    closer = threading.Thread(
        target=lambda: (
            coordinator.close(1, lambda: events.append("restore")),
            closed.set(),
        )
    )
    closer.start()
    assert not closed.wait(timeout=0.05)

    release.set()
    closer.join(timeout=1)

    assert active_future.result(timeout=1) is None
    assert pending_refresh.cancelled()
    assert pending_call.cancelled()
    assert events == ["active", "restore"]
    assert closed.is_set()


def test_submission_after_close_fails_without_creating_executor():
    coordinator = HudCoordinator(generation=0)
    coordinator.close(1, lambda: None)

    future = coordinator.submit_latest(1, lambda: None)

    with pytest.raises(HudClosed):
        future.result(timeout=1)
    assert coordinator._executor is None
