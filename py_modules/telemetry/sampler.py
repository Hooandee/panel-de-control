import asyncio
import time


class TelemetrySampler:
    """Thin asyncio daemon that polls *sample_fn* every *interval* seconds.

    *sample_fn()* returns ``(appid, sample_dict)`` or ``None``.  When it
    returns a tuple the sample is forwarded to *store.add_sample*.

    ``start()`` is idempotent.  ``stop()`` cancels the background task.
    The loop body is wrapped in a broad except so a single bad sample never
    kills the daemon.  ``start()`` is a no-op when no event loop is running
    (safe in unit-test contexts that skip asyncio).
    """

    def __init__(self, store, sample_fn, interval: float = 5.0, flush_every: int = 12) -> None:
        self._store = store
        self._sample_fn = sample_fn
        self._interval = interval
        # Persist to disk every `flush_every` samples (12 × 5 s ≈ 60 s) instead of
        # every sample — spares eMMC wear. A final flush happens on stop().
        self._flush_every = flush_every
        self._since_flush = 0
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no event loop — no-op (unit tests, import time)
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        # Persist whatever was buffered since the last periodic flush.
        self._store.flush()
        self._since_flush = 0

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval)
                result = self._sample_fn()
                if result is not None:
                    appid, sample = result
                    self._store.add_sample(appid, sample, dt=self._interval, ts=time.time())
                    self._since_flush += 1
                    if self._since_flush >= self._flush_every:
                        self._store.flush()
                        self._since_flush = 0
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001 — loop must never die
                pass
