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

    # Re-apply again this many seconds after an AC change: the firmware briefly reverts
    # to its default (an Ally drops to ~12 W on unplug) and a single re-apply mid-
    # transition can be lost, so re-assert once it has settled.
    _AC_SETTLE_RETRIES = (2.0, 4.0)

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
        self._pending = []   # times at which to re-apply (resume delay + AC settle)
        self._task = None

    def _safe_apply(self, ac):
        try:
            self._apply(ac)
        except Exception:  # noqa: BLE001 - one bad apply must not abort check()
            pass

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
            self._pending.append(now + self._wakeup_delay)
        # AC transition → re-apply now, then again as the firmware settles
        if ac != self._last_ac:
            self._last_ac = ac
            self._safe_apply(ac)
            self._pending.extend(now + d for d in self._AC_SETTLE_RETRIES)
        # fire every scheduled re-apply whose delay has elapsed (re-reading AC live)
        due = [t for t in self._pending if now >= t]
        if due:
            self._pending = [t for t in self._pending if now < t]
            self._safe_apply(self._read_ac())

    async def run(self):
        import time
        while True:
            try:
                self.check(time.time())
            except Exception:  # noqa: BLE001 - the poller must never die
                pass
            await asyncio.sleep(self._interval)

    def start(self):
        if self._task is None:
            self._task = asyncio.ensure_future(self.run())

    def stop(self):
        if self._task is not None:
            self._task.cancel()
            self._task = None
