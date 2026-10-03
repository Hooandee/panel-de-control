import threading
import time

import stack_sampler


def _busy(stop):
    while not stop.is_set():
        sum(range(1000))


def test_finds_the_busy_function():
    stop = threading.Event()
    worker = threading.Thread(target=_busy, args=(stop,), daemon=True)
    worker.start()
    try:
        result = stack_sampler.sample(0.3, interval=0.005)
    finally:
        stop.set()
        worker.join()
    assert result["samples"] > 10
    assert any("_busy" in row["stack"] for row in result["top"])


def test_is_bounded():
    started = time.monotonic()
    assert stack_sampler.sample(-1)["seconds"] == 0.1
    assert time.monotonic() - started < 1
