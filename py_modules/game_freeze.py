"""Freezes the running game while a theme's menus are over it.

The game keeps the GPU busy behind Steam's interface and the menus' frames come late (Deck OLED, The Witcher 3:
GPU 100 %, Home p95 50 ms; frozen, GPU 0 % and p95 17 ms). Only the processes Steam launched for the game stop:
its reaper's tree as game_force_close finds it, never the reaper itself, Steam, gamescope or root. A freeze is a
lease the theme renews while its menus are open, and it always thaws by itself: it lasts at most MAX_MS past the
last renewal even if the theme never asks to resume.
"""

import os
import signal
from pathlib import Path
from typing import Callable

import game_force_close
from game_force_close import Process

MAX_MS = 3000


def game_processes(appid: int, proc_root: str | os.PathLike[str] = "/proc") -> list[Process]:
    """The game's processes under its reaper; the reaper keeps the tree and reaps it, so it never stops."""
    table = game_force_close.process_table(proc_root)
    tree = game_force_close.game_tree(table, appid)
    return [process for process in tree if not game_force_close.is_reaper_for(process, appid)]


class GameFreezer:
    """One freeze at a time; a new pause while frozen renews the lease: it only moves the deadline."""

    def __init__(
        self,
        schedule: Callable[[float, Callable[[], None]], object],
        cancel: Callable[[object], None],
        kill: Callable[[int, int], None] = os.kill,
        find: Callable[[int], list[Process]] = game_processes,
        proc_root: str | os.PathLike[str] = "/proc",
        on_change: Callable[[str, dict[str, object]], None] | None = None,
    ) -> None:
        self._schedule = schedule
        self._cancel = cancel
        self._kill = kill
        self._find = find
        self._root = Path(proc_root)
        self._on_change = on_change
        self._frozen: list[Process] = []
        self._appid = 0
        self._timer: object | None = None

    @property
    def frozen(self) -> bool:
        return bool(self._frozen)

    def pause(self, appid: object, ms: object) -> bool:
        number = game_force_close.normalize_appid(appid)
        if number is None or isinstance(ms, bool) or not isinstance(ms, (int, float)):
            return False
        if self._frozen and number != self._appid:
            self.resume()
        if not self._frozen:
            for process in self._find(number):
                try:
                    self._kill(process.pid, signal.SIGSTOP)
                    self._frozen.append(process)
                except OSError:
                    pass
            if not self._frozen:
                return False
            self._appid = number
            self._notify("freeze", {"appid": number, "processes": len(self._frozen)})
        if self._timer is not None:
            self._cancel(self._timer)
        self._timer = self._schedule(max(0, min(int(ms), MAX_MS)) / 1000, self.resume)
        return True

    def resume(self) -> None:
        if self._timer is not None:
            self._cancel(self._timer)
            self._timer = None
        frozen, self._frozen = self._frozen, []
        if not frozen:
            return
        # Only the same process: a pid reused meanwhile belongs to someone else.
        for process in frozen:
            current = game_force_close.read_process(self._root, process.pid)
            if current is None or current.start != process.start:
                continue
            try:
                self._kill(process.pid, signal.SIGCONT)
            except OSError:
                pass
        self._notify("thaw", {"appid": self._appid, "processes": len(frozen)})
        self._appid = 0

    def _notify(self, event: str, fields: dict[str, object]) -> None:
        if self._on_change is None:
            return
        try:
            self._on_change(event, fields)
        except Exception:  # noqa: BLE001
            pass
