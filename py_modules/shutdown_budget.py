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


def run_bounded(fn, timeout_s: float, name: str) -> bool:
    """Run fn on a daemon thread and wait at most timeout_s; False if it is still running.

    Decky kills the plugin process a few seconds after asking it to stop, so a stuck
    syscall must never hold shutdown hostage: the thread is abandoned, not joined."""
    errors = []

    def target():
        try:
            fn()
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    thread = threading.Thread(target=target, name=name, daemon=True)
    thread.start()
    thread.join(max(0.0, timeout_s))
    if thread.is_alive():
        return False
    if errors:
        raise errors[0]
    return True
