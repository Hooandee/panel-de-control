"""Panel's own diary of what the plugin and the user did, kept for a week.

Decky keeps only the newest five plugin logs and deletes the rest every time the
plugin loads, so anything older than a few restarts was lost before a report could
carry it. The diary lives in the plugin's data folder as one JSON-lines file per day,
bounded by age and total size.

Writers never block: records go to a bounded queue drained by one daemon thread,
and a full queue drops the record and counts it instead of waiting. A record that
repeats the previous one is written once; its repeats within a minute become one
more line carrying how many there were (`n`) and when the last was (`last`).
"""
from __future__ import annotations

import contextvars
import functools
import inspect
import json
import logging
import logging.handlers
import os
import queue
import sys
import threading
import time
import traceback
from typing import Any, Callable, Iterator

_FILE_PREFIX = "pdc-"
_FILE_SUFFIX = ".jsonl"
_LEVELS = {"DEBUG": "D", "INFO": "I", "WARNING": "W", "ERROR": "E", "CRITICAL": "C"}
_MAX_MESSAGE = 4000
_MAX_ARGS = 400
_DAY_S = 86_400

active: "Journal | None" = None
_inside_call: contextvars.ContextVar[bool] = contextvars.ContextVar("pdc_journal_inside_call", default=False)


def _day(at: float) -> str:
    return time.strftime("%Y%m%d", time.localtime(at))


def _file_order(name: str) -> tuple[str, int]:
    stem = name[len(_FILE_PREFIX):-len(_FILE_SUFFIX)]
    day, _, segment = stem.partition(".")
    return day, int(segment) if segment.isdigit() else 0


class Journal:
    def __init__(
        self,
        directory: str,
        *,
        retention_days: int = 7,
        max_total_bytes: int = 16 * 1024 * 1024,
        max_file_bytes: int = 4 * 1024 * 1024,
        queue_size: int = 4096,
        coalesce_s: float = 1.5,
        repeat_s: float = 60.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.directory = directory
        self._retention_s = retention_days * _DAY_S
        self._max_total_bytes = max_total_bytes
        self._max_file_bytes = max_file_bytes
        self._coalesce_s = coalesce_s
        self._repeat_s = repeat_s
        self._clock = clock
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._file = None
        self._file_name: str | None = None
        self._file_day: str | None = None
        self._file_segment = 0
        self._pending: dict | None = None
        self._repeat: dict | None = None
        self._last_content: dict | None = None
        self.dropped = 0
        self.write_failures = 0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="pdc-journal", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        thread = self._thread
        if thread is None:
            return
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            self._stopping.set()
        thread.join(timeout)
        self._thread = None

    def write(self, level: str, source: str, message: str, *, at: float | None = None, **fields: Any) -> None:
        record = {
            "t": round(self._clock() if at is None else at, 3),
            "l": _LEVELS.get(level, level[:1] or "I"),
            "s": source,
            "m": message if len(message) <= _MAX_MESSAGE else message[:_MAX_MESSAGE] + "…",
        }
        record.update(fields)
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            self.dropped += 1

    def files(self) -> list[str]:
        try:
            names = [
                name for name in os.listdir(self.directory)
                if name.startswith(_FILE_PREFIX) and name.endswith(_FILE_SUFFIX)
            ]
        except OSError:
            return []
        return [os.path.join(self.directory, name) for name in sorted(names, key=_file_order)]

    def _run(self) -> None:
        try:
            os.makedirs(self.directory, exist_ok=True)
        except OSError:
            self.write_failures += 1
        self._enforce_limits()
        while True:
            try:
                record = self._queue.get(timeout=self._coalesce_s)
            except queue.Empty:
                self._flush_stale()
                self._sync()
                if self._stopping.is_set():
                    break
                continue
            if record is None:
                break
            self._accept(record)
            while True:
                try:
                    record = self._queue.get_nowait()
                except queue.Empty:
                    break
                if record is None:
                    self._stopping.set()
                    break
                self._accept(record)
            self._sync()
            if self._stopping.is_set():
                break
        self._flush_pending()
        self._close_file()

    def _accept(self, record: dict) -> None:
        if record.get("s") == "rpc":
            self._accept_call(record)
            return
        self._flush_call()
        content = {key: value for key, value in record.items() if key != "t"}
        repeat = self._repeat
        if content == self._last_content and (
            repeat is None or record["t"] - repeat["last"] <= self._repeat_s
        ):
            if repeat is None:
                self._repeat = {**record, "n": 1, "last": record["t"]}
            else:
                repeat["n"] += 1
                repeat["last"] = record["t"]
            return
        self._flush_repeat()
        self._append(record)
        self._last_content = content

    def _accept_call(self, record: dict) -> None:
        pending = self._pending
        if (
            pending is not None
            and pending["m"] == record["m"]
            and "r" not in pending
            and record["t"] - pending.get("last", pending["t"]) <= self._coalesce_s
        ):
            pending["a"] = record.get("a")
            pending["last"] = record["t"]
            pending["n"] = pending.get("n", 1) + 1
            if "r" in record:
                pending["r"] = record["r"]
            return
        self._flush_pending()
        self._pending = dict(record)

    def _flush_call(self) -> None:
        if self._pending is not None:
            record, self._pending = self._pending, None
            self._flush_repeat()
            self._append(record)
            self._last_content = None

    def _flush_repeat(self) -> None:
        if self._repeat is not None:
            record, self._repeat = self._repeat, None
            self._append(record)

    def _flush_pending(self) -> None:
        self._flush_call()
        self._flush_repeat()

    def _flush_stale(self) -> None:
        now = self._clock()
        if self._pending is not None and now - self._pending.get("last", self._pending["t"]) > self._coalesce_s:
            self._flush_call()
        if self._repeat is not None and now - self._repeat["last"] > self._repeat_s:
            self._flush_repeat()

    def _append(self, record: dict) -> None:
        try:
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
            day = _day(record["t"])
            if self._file is None or self._file_day != day:
                self._open(day, 0)
            while self._file.tell() >= self._max_file_bytes:
                self._open(day, self._file_segment + 1)
            self._file.write(line)
        except Exception:  # noqa: BLE001
            self.write_failures += 1

    def _open(self, day: str, segment: int) -> None:
        self._close_file()
        suffix = f".{segment}" if segment else ""
        name = f"{_FILE_PREFIX}{day}{suffix}{_FILE_SUFFIX}"
        self._file = open(os.path.join(self.directory, name), "a", encoding="utf-8")
        self._file_name = name
        self._file_day = day
        self._file_segment = segment
        self._enforce_limits()

    def _sync(self) -> None:
        try:
            if self._file is not None:
                self._file.flush()
        except Exception:  # noqa: BLE001
            self.write_failures += 1

    def _close_file(self) -> None:
        try:
            if self._file is not None:
                self._file.close()
        except Exception:  # noqa: BLE001
            pass
        self._file = None
        self._file_name = None

    def _enforce_limits(self) -> None:
        cutoff = _day(self._clock() - self._retention_s)
        sized: list[tuple[str, int]] = []
        for path in self.files():
            day = os.path.basename(path)[len(_FILE_PREFIX):len(_FILE_PREFIX) + 8]
            try:
                if day < cutoff:
                    os.unlink(path)
                    continue
                sized.append((path, os.path.getsize(path)))
            except OSError:
                continue
        total = sum(size for _, size in sized)
        current = os.path.join(self.directory, self._file_name) if self._file_name else None
        for path, size in sized:
            if total <= self._max_total_bytes:
                break
            if path == current:
                continue
            try:
                os.unlink(path)
                total -= size
            except OSError:
                continue


def read_records(directory: str) -> Iterator[dict]:
    """Every readable record, oldest file first. Corrupt lines are skipped."""
    journal = Journal(directory)
    for path in journal.files():
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(record, dict):
                        yield record
        except OSError:
            continue


_KEY_SOURCES = ("rpc", "session", "context", "sections", "state", "tdp", "loop")
_KEY_MESSAGES = ("TDP transition", "Lifecycle transition", "Shutdown stage", " loaded (euid")


def _is_key_record(record: dict) -> bool:
    if record.get("l") in ("W", "E", "C") or record.get("s") in _KEY_SOURCES:
        return True
    message = record.get("m")
    return isinstance(message, str) and any(key in message for key in _KEY_MESSAGES)


def collect(
    directory: str,
    *,
    now: float | None = None,
    recent_s: float = _DAY_S,
    recent_bytes: int = 700_000,
    older_bytes: int = 500_000,
) -> dict:
    """What a report carries: every record of the last day, then only warnings,
    errors, user actions, sessions and power/lifecycle transitions of the older
    days. Each part keeps its newest records within its byte budget."""
    now = time.time() if now is None else now
    recent: list[dict] = []
    older: list[dict] = []
    for record in read_records(directory):
        at = record.get("t")
        if not isinstance(at, (int, float)):
            continue
        if at >= now - recent_s:
            recent.append(record)
        elif _is_key_record(record):
            older.append(record)

    def newest_within(records: list[dict], budget: int) -> tuple[list[dict], int]:
        kept: list[dict] = []
        for record in reversed(records):
            size = len(json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str)) + 1
            if size > budget:
                break
            budget -= size
            kept.append(record)
        kept.reverse()
        return kept, len(records) - len(kept)

    recent_kept, recent_cut = newest_within(recent, recent_bytes)
    older_kept, older_cut = newest_within(older, older_bytes)
    files = []
    for path in Journal(directory).files():
        try:
            files.append({"name": os.path.basename(path), "bytes": os.path.getsize(path)})
        except OSError:
            continue
    return {
        "schema": 1,
        "summary": summarize(recent + older),
        "files": files,
        "recent": recent_kept,
        "recent_omitted": recent_cut,
        "older": older_kept,
        "older_omitted": older_cut,
    }


def _count(record: dict) -> int:
    count = record.get("n", 1)
    return count if isinstance(count, int) and count > 0 else 1


def summarize(records: list[dict], *, top: int = 5) -> list[dict]:
    """One short entry per session, oldest first: what to read before any line."""
    sessions: list[dict] = []
    current: dict | None = None
    for record in sorted(records, key=lambda item: item.get("t", 0)):
        if record.get("s") == "session" and record.get("m") == "start" or current is None:
            current = {
                "start": record.get("t"),
                "end": record.get("t"),
                "version": record.get("version"),
                "games": [],
                "tdp_w": None,
                "max_temp_c": None,
                "rivals": [],
                "external_writes": 0,
                "actions": 0,
                "state_changes": {},
                "_problems": {},
            }
            sessions.append(current)
        current["end"] = record.get("last", record.get("t"))
        source = record.get("s")
        if source == "session" and record.get("m") == "stop":
            current["stopped"] = True
        elif source == "rpc":
            current["actions"] += _count(record)
        elif source == "context":
            current["rivals"] = [rival.get("name") for rival in record.get("rivals") or []]
        elif source == "tdp" and record.get("m") == "external_write":
            current["external_writes"] += 1
        elif source == "state":
            changes = current["state_changes"]
            changes[record.get("m")] = changes.get(record.get("m"), 0) + 1
            game = record.get("game")
            if game is not None and game not in current["games"]:
                current["games"].append(game)
            tdp = record.get("tdp_w")
            if isinstance(tdp, (int, float)):
                low, high = current["tdp_w"] or (tdp, tdp)
                current["tdp_w"] = [min(low, tdp), max(high, tdp)]
            for key in ("cpu_c", "gpu_c"):
                value = record.get(key)
                if isinstance(value, (int, float)):
                    current["max_temp_c"] = max(current["max_temp_c"] or value, value)
        if record.get("l") in ("W", "E", "C"):
            key = (record.get("l"), str(record.get("m", ""))[:120])
            current["_problems"][key] = current["_problems"].get(key, 0) + _count(record)
    for session in sessions:
        problems = session.pop("_problems")
        session["problems"] = [
            {"level": level, "message": message, "count": count}
            for (level, message), count in sorted(problems.items(), key=lambda item: -item[1])[:top]
        ]
        session["problem_kinds"] = len(problems)
    return sessions


class LoopWatchdog:
    """Notices when the asyncio loop stops answering. A coroutine on the loop
    stamps a heartbeat; a thread checks it, and the first time it is older than
    the limit writes one warning with the loop thread's stack, then one more line
    when the loop answers again with how long it was stuck."""

    def __init__(
        self,
        journal: Journal,
        *,
        limit_s: float = 3.0,
        beat_s: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._journal = journal
        self._limit_s = limit_s
        self._beat_s = beat_s
        self._clock = clock
        self._last_beat = clock()
        self._loop_thread: int | None = None
        self._stuck_since: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    async def beat(self) -> None:
        import asyncio

        self._loop_thread = threading.get_ident()
        while not self._stop.is_set():
            self._last_beat = self._clock()
            await asyncio.sleep(self._beat_s)

    def start(self) -> None:
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._watch, name="pdc-loop-watchdog", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread = None

    def check(self) -> None:
        now = self._clock()
        late = now - self._last_beat
        if late >= self._limit_s and self._stuck_since is None:
            self._stuck_since = self._last_beat
            self._journal.write("WARNING", "loop", "blocked", after_s=round(late, 1), stack=self._loop_stack())
        elif late < self._limit_s and self._stuck_since is not None:
            self._journal.write("WARNING", "loop", "recovered", stuck_s=round(self._last_beat - self._stuck_since, 1))
            self._stuck_since = None

    def _loop_stack(self) -> str:
        frame = sys._current_frames().get(self._loop_thread) if self._loop_thread else None
        if frame is None:
            return ""
        return "".join(traceback.format_stack(frame)[-12:])[-3000:]

    def _watch(self) -> None:
        while not self._stop.wait(self._beat_s):
            self.check()


class JournalHandler(logging.Handler):
    """Copies every log record of the plugin process into the diary."""

    def __init__(self, journal: Journal) -> None:
        super().__init__(logging.INFO)
        self._journal = journal

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if record.exc_info:
                message = f"{message}\n{logging.Formatter().formatException(record.exc_info)}"
            source = "log" if record.name == "root" else record.name
            self._journal.write(record.levelname, source, message, at=record.created)
        except Exception:  # noqa: BLE001
            pass


class _DroppingQueueHandler(logging.handlers.QueueHandler):
    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            pass


def queue_logger_handlers(logger: logging.Logger, *, queue_size: int = 4096) -> Callable[[], None]:
    """Moves the logger's existing handlers (Decky's log file and stdout) behind a
    queue drained by a background thread, so logging never waits on disk. Returns
    the call that puts them back."""
    handlers = [handler for handler in logger.handlers if not isinstance(handler, JournalHandler)]
    if not handlers:
        return lambda: None
    records: queue.Queue = queue.Queue(maxsize=queue_size)
    front = _DroppingQueueHandler(records)
    listener = logging.handlers.QueueListener(records, *handlers, respect_handler_level=True)
    listener.start()
    for handler in handlers:
        logger.removeHandler(handler)
    logger.addHandler(front)

    def restore() -> None:
        logger.removeHandler(front)
        listener.stop()
        for handler in handlers:
            logger.addHandler(handler)

    return restore


def _summary(value: Any) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:  # noqa: BLE001
        text = repr(value)
    return text if len(text) <= _MAX_ARGS else text[:_MAX_ARGS] + "…"


def _outcome(result: Any) -> dict | None:
    if isinstance(result, dict) and result.get("ok") is False:
        detail = result.get("error") or result.get("detail") or result.get("reason")
        return {"ok": False, "error": _summary(detail)[:160]} if detail is not None else {"ok": False}
    return None


def trace_calls(
    cls: type,
    *,
    untraced_prefixes: tuple[str, ...] = ("_", "get_", "list_", "check_", "record_"),
    untraced: frozenset[str] = frozenset(),
    hidden_arguments: frozenset[str] = frozenset(),
) -> None:
    """Wraps the frontend-callable coroutines that change something so each call,
    its arguments and a failed outcome land in the diary as a user action. Calls of
    the same method within the coalescing window collapse into one record, and calls
    made from inside another traced call are the backend's own, not the user's."""
    for name, function in list(vars(cls).items()):
        if name.startswith(untraced_prefixes) or name in untraced or not inspect.iscoroutinefunction(function):
            continue
        setattr(cls, name, _traced(name, function, name in hidden_arguments))


def _traced(name: str, function: Callable, hide_arguments: bool) -> Callable:
    @functools.wraps(function)
    async def call(self, *args, **kwargs):
        journal = active
        if journal is None or _inside_call.get():
            return await function(self, *args, **kwargs)
        arguments = None if hide_arguments else _summary(list(args) + ([kwargs] if kwargs else []))
        token = _inside_call.set(True)
        try:
            result = await function(self, *args, **kwargs)
        except Exception as error:
            journal.write("ERROR", "rpc", name, a=arguments, r={"raised": type(error).__name__})
            raise
        finally:
            _inside_call.reset(token)
        outcome = _outcome(result)
        if outcome is None:
            journal.write("INFO", "rpc", name, a=arguments)
        else:
            journal.write("WARNING", "rpc", name, a=arguments, r=outcome)
        return result

    return call
