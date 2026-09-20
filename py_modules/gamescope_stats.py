"""Small, failure-safe reader for Gamescope's performance-statistics FIFO."""

import glob
import math
import os
import select
import threading
import time


class GamescopeStats:
    def __init__(self, root="/", clock=time.monotonic, stale_after_s=5.0):
        self._root = root
        self._clock = clock
        self._stale_after_s = max(0.1, float(stale_after_s))
        self._fps = None
        self._fps_at = None
        self._focus = None
        self._unread_min_fps = None
        self._unread_focus = None
        self._unread_sample_at = None
        self._pending_fps = None
        self._pending_fps_at = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._pipe_available = None
        self._connected = False
        self._last_error = None

    def _clear_samples_locked(self):
        self._fps = None
        self._fps_at = None
        self._unread_min_fps = None
        self._unread_focus = None
        self._unread_sample_at = None
        self._pending_fps = None
        self._pending_fps_at = None

    def _apply_line(self, line):
        if not isinstance(line, str):
            return
        if line.startswith("fps="):
            try:
                fps = float(line[4:])
            except (TypeError, ValueError, OverflowError):
                with self._lock:
                    self._clear_samples_locked()
                return
            if not math.isfinite(fps) or fps < 0:
                with self._lock:
                    self._clear_samples_locked()
                return
            with self._lock:
                self._pending_fps = fps
                self._pending_fps_at = self._clock()
            return
        if not line.startswith("focus="):
            return
        focus = line[6:] or None
        with self._lock:
            self._focus = focus
            if self._pending_fps is not None:
                self._fps = self._pending_fps
                self._fps_at = self._pending_fps_at
                if self._unread_focus != focus or self._unread_min_fps is None:
                    self._unread_min_fps = self._pending_fps
                else:
                    self._unread_min_fps = min(
                        self._unread_min_fps,
                        self._pending_fps,
                    )
                self._unread_focus = focus
                self._unread_sample_at = self._pending_fps_at
                self._pending_fps = None
                self._pending_fps_at = None
            else:
                self._clear_samples_locked()

    def _pipe_path(self):
        pattern = os.path.join(
            self._root,
            "run",
            "user",
            "*",
            "gamescope*",
            "stats.pipe",
        )
        candidates = []
        for path in glob.glob(pattern):
            try:
                candidates.append((os.path.getmtime(path), path))
            except OSError:
                continue
        return max(candidates)[1] if candidates else None

    def _run(self):
        while not self._stop_event.is_set():
            path = self._pipe_path()
            with self._lock:
                self._pipe_available = path is not None
            if path is None:
                self._stop_event.wait(2.0)
                continue
            try:
                flags = os.O_RDONLY | os.O_NONBLOCK
                flags |= getattr(os, "O_CLOEXEC", 0)
                descriptor = os.open(path, flags)
            except OSError as error:
                with self._lock:
                    self._connected = False
                    self._last_error = {
                        "phase": "open",
                        "type": type(error).__name__,
                    }
                self._stop_event.wait(1.0)
                continue
            with self._lock:
                self._connected = True
                self._last_error = None
            buffer = ""
            try:
                while not self._stop_event.is_set():
                    readable, _writable, _errors = select.select(
                        [descriptor], [], [], 1.0
                    )
                    if not readable:
                        continue
                    chunk = os.read(descriptor, 4096)
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        self._apply_line(line.strip())
            except OSError as error:
                with self._lock:
                    self._last_error = {
                        "phase": "read",
                        "type": type(error).__name__,
                    }
            finally:
                os.close(descriptor)
                with self._lock:
                    self._connected = False
            self._stop_event.wait(1.0)

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="gamescope-stats",
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
            if not thread.is_alive():
                self._thread = None
        self.clear()

    def clear(self):
        with self._lock:
            self._focus = None
            self._clear_samples_locked()

    def diagnostics(self):
        with self._lock:
            focus = self._focus
            fps = self._fps
            fps_at = self._fps_at
            pending_min = self._unread_min_fps
            pipe_available = self._pipe_available
            connected = self._connected
            last_error = dict(self._last_error) if self._last_error else None
        now = self._clock()
        age = None if fps_at is None else max(0.0, now - fps_at)
        focus_kind = None if focus is None else "steam" if focus == "steam" else "game"
        if focus_kind in (None, "steam"):
            reason = "no_game_focus"
        elif fps is None or age is None:
            reason = "fps_unavailable"
        elif age > self._stale_after_s:
            reason = "fps_stale"
        else:
            reason = "ok"
        thread = self._thread
        return {
            "reader_alive": bool(thread is not None and thread.is_alive()),
            "pipe_available": pipe_available,
            "connected": connected,
            "last_error": last_error,
            "sample_available": reason == "ok",
            "sample_age_s": age,
            "reason": reason,
            "focus": focus_kind,
            "fps": fps,
            "pending_min_fps": pending_min,
        }

    def read(self):
        with self._lock:
            focus = self._focus
            if self._unread_focus == focus and self._unread_min_fps is not None:
                fps = self._unread_min_fps
                fps_at = self._unread_sample_at
            else:
                fps = self._fps
                fps_at = self._fps_at
            self._unread_min_fps = None
            self._unread_focus = None
            self._unread_sample_at = None
        now = self._clock()
        age = None if fps_at is None else max(0.0, now - fps_at)
        if focus is None or focus == "steam":
            reason = "no_game_focus"
        elif fps is None or age is None:
            reason = "fps_unavailable"
        elif age > self._stale_after_s:
            reason = "fps_stale"
        else:
            return {
                "fps": fps,
                "focus": focus,
                "age_s": age,
                "sample_at": fps_at,
                "available": True,
                "reason": "ok",
            }
        return {
            "fps": None,
            "focus": focus,
            "age_s": age,
            "sample_at": fps_at,
            "available": False,
            "reason": reason,
        }
