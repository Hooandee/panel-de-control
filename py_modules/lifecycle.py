import asyncio
import glob
import os


def read_on_ac(root="/"):
    """True if any power supply of type 'Mains' is online. Never raises."""
    for d in glob.glob(os.path.join(root, "sys/class/power_supply", "*")):
        try:
            with open(os.path.join(d, "type")) as f:
                if f.read().strip() != "Mains":
                    continue
            with open(os.path.join(d, "online")) as f:
                if f.read().strip() == "1":
                    return True
        except OSError:
            continue
    return False


def _read_wakeup_count(root="/"):
    try:
        with open(os.path.join(root, "sys/power/wakeup_count")) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


class LifecycleManager:
    """Re-applies TDP after resume (wakeup_count change, delayed) and on AC/DC transitions.
    Decision logic is in check(now); run() is a thin async loop around it."""

    def __init__(self, apply_cb, root="/", wakeup_delay=4.0, interval=2.0,
                 read_wakeup=None, read_ac=None):
        self._apply = apply_cb
        self._root = root
        self._wakeup_delay = wakeup_delay
        self._interval = interval
        self._read_wakeup = read_wakeup or (lambda: _read_wakeup_count(root))
        self._read_ac = read_ac or (lambda: read_on_ac(root))
        self._last_wakeup = None
        self._last_ac = None
        self._pending_apply_at = None
        self._task = None

    def check(self, now):
        wc = self._read_wakeup()
        ac = self._read_ac()
        # initialize on first observation (no event)
        if self._last_wakeup is None:
            self._last_wakeup, self._last_ac = wc, ac
            return
        # resume detected → schedule a delayed re-apply
        if wc != self._last_wakeup:
            self._last_wakeup = wc
            self._pending_apply_at = now + self._wakeup_delay
        # AC transition → re-apply immediately
        if ac != self._last_ac:
            self._last_ac = ac
            self._apply(ac)
        # fire a scheduled re-apply once its delay elapses
        if self._pending_apply_at is not None and now >= self._pending_apply_at:
            self._pending_apply_at = None
            self._apply(ac)

    async def run(self):
        import time
        while True:
            self.check(time.time())
            await asyncio.sleep(self._interval)

    def start(self):
        if self._task is None:
            self._task = asyncio.ensure_future(self.run())

    def stop(self):
        if self._task is not None:
            self._task.cancel()
            self._task = None
