"""Reader for the gamescope stats FIFO.

Gamescope writes repeating lines such as::

    fps=76.942802
    focus=3768760

to a named pipe at ``/run/user/<uid>/gamescope-stats/stats.pipe``.
``focus`` is the focused Steam appid (a numeric string) or ``"steam"`` when
the Steam UI / overlay is active (i.e. no game is currently focused).

``GamescopeStats`` spawns a daemon thread that opens the FIFO, reads lines
forever, and caches the latest ``fps`` / ``focus`` values.  ``game_fps()``
returns the cached FPS only when a real game is focused (not "steam", not
None).  Never raises; degrades gracefully when the FIFO does not exist.
"""

import glob
import os
import threading
import time


def parse_stats(text: str) -> dict:
    """Parse a text blob from the stats pipe.

    Returns ``{"fps": float|None, "focus": str|None}`` from the LAST complete
    ``fps=`` / ``focus=`` lines.  Partial trailing lines (no newline) are
    ignored.  Garbage / non-parseable lines are silently skipped.  Never
    raises.
    """
    fps = None
    focus = None
    try:
        # Only process lines that are complete (terminated by a newline).
        # A partial trailing line — i.e., text that does not end with '\n' —
        # may represent an in-progress write from gamescope; skip it.
        if text.endswith("\n"):
            lines = text.splitlines()
        else:
            lines = text.splitlines()[:-1]  # drop the potentially incomplete tail
        for raw in lines:
            line = raw.strip()
            if line.startswith("fps="):
                try:
                    fps = float(line[4:])
                except ValueError:
                    pass
            elif line.startswith("focus="):
                focus = line[6:] or None
    except Exception:  # noqa: BLE001
        pass
    return {"fps": fps, "focus": focus}


class GamescopeStats:
    """Background reader for the gamescope stats named pipe.

    Parameters
    ----------
    root:
        Filesystem root prefix (override in tests).
    """

    def __init__(self, root: str = "/"):
        self._root = root
        self._fps: float | None = None
        self._focus: str | None = None
        self._stop = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Internal helpers (pure, testable without a real FIFO)
    # ------------------------------------------------------------------

    def _apply_line(self, line: str) -> None:
        """Apply a single stripped line to cached state.  Never raises."""
        try:
            if line.startswith("fps="):
                try:
                    self._fps = float(line[4:])
                except ValueError:
                    pass
            elif line.startswith("focus="):
                val = line[6:]
                self._focus = val if val else None
        except Exception:  # noqa: BLE001
            pass

    def _pipe_path(self) -> str | None:
        pattern = os.path.join(self._root, "run", "user", "*",
                               "gamescope-stats", "stats.pipe")
        matches = sorted(glob.glob(pattern))
        return matches[0] if matches else None

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Daemon thread: open the FIFO and read lines forever."""
        while not self._stop:
            path = self._pipe_path()
            if path is None:
                time.sleep(2)
                continue
            try:
                with open(path) as fh:
                    for raw in fh:
                        if self._stop:
                            return
                        self._apply_line(raw.strip())
            except (OSError, IOError):
                pass
            if not self._stop:
                time.sleep(1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch the background reader thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="gamescope-stats")
        self._thread.start()

    def stop(self) -> None:
        """Signal the background thread to exit."""
        self._stop = True

    def read(self) -> dict:
        """Return cached ``{"fps": float|None, "focus": str|None}``.

        ``fps`` is set to ``None`` when ``focus`` is ``"steam"`` or ``None``
        (i.e. no game is focused) so callers never see stale FPS from a
        previous game session.
        """
        fps = self.game_fps()
        return {"fps": fps, "focus": self._focus}

    def game_fps(self) -> float | None:
        """FPS of the currently focused game, or ``None`` if no game is active."""
        if self._focus is None or self._focus == "steam":
            return None
        return self._fps
