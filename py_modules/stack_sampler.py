"""Where the backend spends its time: samples every thread's Python stack for a few seconds.

Read-only and bounded; for chasing CPU use on devices without a profiler (py-spy does not run under
FEX on ARM handhelds).
"""

import collections
import sys
import threading
import time

MAX_SECONDS = 10.0
DEPTH = 8


def _frame_key(frame) -> str:
    parts = []
    while frame is not None and len(parts) < DEPTH:
        code = frame.f_code
        parts.append(f"{code.co_filename.rsplit('/', 1)[-1]}:{frame.f_lineno}:{code.co_name}")
        frame = frame.f_back
    return " < ".join(parts)


def sample(seconds: float = 5.0, interval: float = 0.01, top: int = 15) -> dict:
    seconds = max(0.1, min(float(seconds), MAX_SECONDS))
    me = threading.get_ident()
    counts: collections.Counter[str] = collections.Counter()
    samples = 0
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for ident, frame in sys._current_frames().items():
            if ident != me:
                counts[_frame_key(frame)] += 1
        samples += 1
        time.sleep(interval)
    native = {thread.ident: (thread.native_id, thread.name) for thread in threading.enumerate()}
    last = {
        str(native.get(ident, (ident, "?"))[0]): f"{native.get(ident, (ident, '?'))[1]}: {_frame_key(frame)}"
        for ident, frame in sys._current_frames().items()
        if ident != me
    }
    return {
        "seconds": seconds,
        "by_thread": last,
        "samples": samples,
        "threads": threading.active_count(),
        "top": [{"stack": stack, "share": round(n / max(1, samples), 3)} for stack, n in counts.most_common(top)],
    }
