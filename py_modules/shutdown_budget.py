import threading
import time


class ShutdownBudget:
    def __init__(self, total_s: float, clock=time.monotonic) -> None:
        self._clock = clock
        self._deadline = clock() + total_s

    def remaining(self) -> float:
        return max(0.0, self._deadline - self._clock())

    def slice(self, cap_s: float, reserve_s: float = 0.0) -> float:
        return max(0.0, min(cap_s, self.remaining() - reserve_s))


class BoundedWork:
    """fn on a daemon thread that shutdown can stop waiting for.

    Decky kills the plugin process a few seconds after asking it to stop, so a stuck
    syscall must never hold shutdown hostage: the thread is abandoned, not joined."""

    def __init__(self, fn, name: str) -> None:
        self.name = name
        self.error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, args=(fn,), name=name, daemon=True)
        self._thread.start()

    def _run(self, fn) -> None:
        try:
            fn()
        except BaseException as error:  # noqa: BLE001
            self.error = error

    @property
    def done(self) -> bool:
        return not self._thread.is_alive()

    def join(self, timeout_s: float) -> bool:
        self._thread.join(max(0.0, timeout_s))
        return self.done


def run_bounded(fn, timeout_s: float, name: str) -> bool:
    """False if fn is still running after timeout_s; re-raises what fn raised."""
    work = BoundedWork(fn, name)
    if not work.join(timeout_s):
        return False
    if work.error is not None:
        raise work.error
    return True
