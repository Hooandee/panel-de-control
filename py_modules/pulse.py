"""Black box for hard freezes. A frozen device loses the last minutes of the system
journal (journald syncs every few minutes) and of Panel's own diary (flushed, not
synced), so a forced reboot leaves no trace of how the machine died.

Every few seconds a small file is rewritten and fsynced with the last samples of
memory pressure, GPU load, the Steam client's memory and Panel's last diary lines.
A clean stop marks it; at the next start an unmarked file is set aside as the
record of an unclean end.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import threading
import time
from typing import Any, Callable

_FILE = "pulse.json"
_UNCLEAN_PREFIX = "pulse-unclean-"
_KEEP_UNCLEAN = 4
_WATCHED_PROCESSES = ("steamwebhelper", "steam", "gamescope", "gamescope-wl", "python3", "PluginLoader")


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def boot_id(root: str = "/") -> str | None:
    value = _read(os.path.join(root, "proc/sys/kernel/random/boot_id"))
    return value.strip() if value else None


def _meminfo(root: str) -> dict:
    text = _read(os.path.join(root, "proc/meminfo")) or ""
    values = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            values[name] = int(parts[0]) // 1024
    return {
        "avail_mb": values.get("MemAvailable"),
        "swap_free_mb": values.get("SwapFree"),
        "swap_total_mb": values.get("SwapTotal"),
    }


def _pressure(root: str, resource: str) -> float | None:
    text = _read(os.path.join(root, "proc/pressure", resource)) or ""
    for line in text.splitlines():
        if line.startswith("some "):
            for field in line.split():
                if field.startswith("avg10="):
                    try:
                        return float(field[6:])
                    except ValueError:
                        return None
    return None


def _number(path: str) -> int | None:
    value = _read(path)
    try:
        return int(value.strip()) if value else None
    except ValueError:
        return None


def _gpu(root: str) -> dict | None:
    for device in sorted(glob.glob(os.path.join(root, "sys/class/drm/card*/device"))):
        busy = _number(os.path.join(device, "gpu_busy_percent"))
        if busy is None:
            continue
        vram = _number(os.path.join(device, "mem_info_vram_used"))
        gtt = _number(os.path.join(device, "mem_info_gtt_used"))
        return {
            "busy": busy,
            "vram_mb": vram // 1048576 if vram is not None else None,
            "gtt_mb": gtt // 1048576 if gtt is not None else None,
        }
    return None


def _processes(root: str) -> dict:
    page_kb = os.sysconf("SC_PAGE_SIZE") // 1024 if hasattr(os, "sysconf") else 4
    usage: dict[str, dict] = {}
    for entry in glob.glob(os.path.join(root, "proc/[0-9]*")):
        name = (_read(os.path.join(entry, "comm")) or "").strip()
        if name not in _WATCHED_PROCESSES:
            continue
        statm = (_read(os.path.join(entry, "statm")) or "").split()
        if len(statm) < 2 or not statm[1].isdigit():
            continue
        slot = usage.setdefault(name, {"n": 0, "rss_mb": 0})
        slot["n"] += 1
        slot["rss_mb"] += int(statm[1]) * page_kb // 1024
    return usage


def system_sample(root: str = "/") -> dict:
    loadavg = (_read(os.path.join(root, "proc/loadavg")) or "").split()
    uptime = (_read(os.path.join(root, "proc/uptime")) or "").split()
    return {
        "up": float(uptime[0]) if uptime else None,
        "load1": float(loadavg[0]) if loadavg else None,
        **_meminfo(root),
        "psi_mem": _pressure(root, "memory"),
        "psi_io": _pressure(root, "io"),
        "psi_cpu": _pressure(root, "cpu"),
        "gpu": _gpu(root),
        "proc": _processes(root),
    }


def _write_synced(path: str, payload: dict) -> None:
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class Pulse:
    def __init__(
        self,
        directory: str,
        *,
        context: Callable[[], dict] | None = None,
        recent: Callable[[], list] | None = None,
        on_unclean: Callable[[dict], None] | None = None,
        sample: Callable[[], dict] = system_sample,
        interval_s: float = 10.0,
        keep: int = 30,
        clock: Callable[[], float] = time.time,
        current_boot: Callable[[], str | None] = boot_id,
    ) -> None:
        self.directory = directory
        self._context = context
        self._recent = recent
        self._on_unclean = on_unclean
        self._sample = sample
        self._interval_s = interval_s
        self._samples: collections.deque = collections.deque(maxlen=keep)
        self._clock = clock
        self._boot = current_boot()
        self._started = clock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.write_failures = 0

    @property
    def path(self) -> str:
        return os.path.join(self.directory, _FILE)

    def set_aside_previous(self) -> dict | None:
        """Keeps the previous run's file when it ended without a clean stop and
        returns how it ended."""
        previous = _load(self.path)
        if previous is None or previous.get("stopped"):
            return None
        end = summarize_unclean(previous, self._boot)
        name = f"{_UNCLEAN_PREFIX}{int(end['last_t'] or previous.get('started') or self._clock())}.json"
        try:
            _write_synced(os.path.join(self.directory, name), {**previous, "end": end})
            os.remove(self.path)
        except OSError:
            self.write_failures += 1
            return None
        _prune(self.directory)
        return end

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pdc-pulse", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(1.0)
        self._persist(stopped=True)

    def tick(self) -> None:
        try:
            sample = {"t": round(self._clock(), 1), **self._sample()}
        except Exception as error:  # noqa: BLE001
            sample = {"t": round(self._clock(), 1), "error": type(error).__name__}
        if self._context is not None:
            try:
                sample["ctx"] = self._context()
            except Exception:  # noqa: BLE001
                pass
        self._samples.append(sample)
        self._persist(stopped=False)

    def _persist(self, *, stopped: bool) -> None:
        payload: dict[str, Any] = {
            "boot": self._boot,
            "started": round(self._started, 1),
            "interval_s": self._interval_s,
            "stopped": stopped,
            "samples": list(self._samples),
        }
        if self._recent is not None:
            try:
                payload["recent"] = self._recent()
            except Exception:  # noqa: BLE001
                pass
        try:
            os.makedirs(self.directory, exist_ok=True)
            _write_synced(self.path, payload)
        except OSError:
            self.write_failures += 1

    def _run(self) -> None:
        end = self.set_aside_previous()
        if end is not None and self._on_unclean is not None:
            try:
                self._on_unclean(end)
            except Exception:  # noqa: BLE001
                self.write_failures += 1
        while True:
            self.tick()
            if self._stop.wait(self._interval_s):
                return


def _load(path: str) -> dict | None:
    text = _read(path)
    if not text:
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _unclean_files(directory: str) -> list[str]:
    return sorted(glob.glob(os.path.join(directory, f"{_UNCLEAN_PREFIX}*.json")))


def _prune(directory: str) -> None:
    for path in _unclean_files(directory)[:-_KEEP_UNCLEAN]:
        try:
            os.remove(path)
        except OSError:
            pass


def summarize_unclean(previous: dict, current_boot: str | None) -> dict:
    samples = previous.get("samples") or []
    last = samples[-1] if samples else {}
    return {
        "started": previous.get("started"),
        "last_t": last.get("t"),
        "ran_s": round(last["t"] - previous["started"], 1)
        if isinstance(last.get("t"), (int, float)) and isinstance(previous.get("started"), (int, float))
        else None,
        "system_rebooted": previous.get("boot") != current_boot if previous.get("boot") and current_boot else None,
        "last": last,
    }


def report(directory: str) -> dict:
    """The live black box plus every kept unclean end, for the report bundle."""
    unclean = []
    for path in _unclean_files(directory):
        previous = _load(path)
        if previous is not None:
            unclean.append({**(previous.get("end") or {}), "samples": previous.get("samples"),
                            "recent": previous.get("recent")})
    return {"schema": 1, "current": _load(os.path.join(directory, _FILE)), "unclean": unclean}
