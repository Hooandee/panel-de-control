from collections import deque
import concurrent.futures
from dataclasses import dataclass
import threading


class HudClosed(RuntimeError):
    pass


class HudStale(RuntimeError):
    pass


@dataclass
class _Work:
    generation: int
    fn: object
    future: concurrent.futures.Future


def _failed(error):
    future = concurrent.futures.Future()
    future.set_exception(error)
    return future


class HudCoordinator:
    def __init__(self, generation=0):
        self._generation = generation
        self._lock = threading.Lock()
        self._queue = deque()
        self._latest = None
        self._executor = None
        self._runner = None
        self._closed = False

    def _ensure_executor_locked(self):
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        return self._executor

    def _start_runner_locked(self):
        if self._runner is None:
            executor = self._ensure_executor_locked()
            self._runner = executor.submit(self._drain)

    def _enqueue(self, generation, fn, *, replaceable):
        with self._lock:
            if self._closed:
                return _failed(HudClosed("HUD coordinator is closed"))
            if generation != self._generation:
                return _failed(HudStale("HUD generation is stale"))
            future = concurrent.futures.Future()
            work = _Work(generation, fn, future)
            if replaceable and self._latest is not None:
                previous = self._latest
                previous.future.cancel()
                for index, queued in enumerate(self._queue):
                    if queued is previous:
                        self._queue[index] = work
                        break
                self._latest = work
            else:
                self._queue.append(work)
                if replaceable:
                    self._latest = work
            self._start_runner_locked()
            return future

    def submit_latest(self, generation, fn):
        return self._enqueue(generation, fn, replaceable=True)

    def call(self, generation, fn):
        return self._enqueue(generation, fn, replaceable=False)

    def _drain(self):
        while True:
            with self._lock:
                if not self._queue:
                    self._runner = None
                    return
                work = self._queue.popleft()
                if work is self._latest:
                    self._latest = None
                stale = work.generation != self._generation
            if stale:
                work.future.set_exception(HudStale("HUD generation is stale"))
                continue
            if not work.future.set_running_or_notify_cancel():
                continue
            try:
                result = work.fn()
            except BaseException as error:
                work.future.set_exception(error)
            else:
                work.future.set_result(result)

    def close(self, generation, restore):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._generation = generation
            for work in self._queue:
                work.future.cancel()
            self._queue.clear()
            self._latest = None
            executor = self._executor
        if executor is None:
            restore()
            return
        restore_future = executor.submit(restore)
        try:
            restore_future.result()
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
            with self._lock:
                self._executor = None
                self._runner = None
