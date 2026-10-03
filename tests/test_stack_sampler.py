import threading
import time

import stack_sampler
from test_tdp_guard_rpc import plugin  # noqa: F401


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


def test_backend_sample_reports_who_offloads_work(plugin):  # noqa: F811
    import asyncio

    async def run():
        async def busy():
            for _ in range(3):
                await asyncio.to_thread(sum, [1, 2])
        task = asyncio.create_task(busy())
        result = await plugin.sample_backend_stacks(0.2)
        await task
        return result

    result = asyncio.run(run())
    assert result["offloaded"].get("sum", 0) == 3
