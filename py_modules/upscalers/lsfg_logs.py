"""Retain a bounded tail without replacing a log still open in a game process."""

import os
import re
import stat
import threading
from pathlib import Path

MAX_BYTES = 256 * 1024
RETAIN_BYTES = 128 * 1024
REPORT_BYTES = 64 * 1024
INTERVAL = 5.0
_SECRET = re.compile(r"(?i)\b(token|password|secret|authorization|api[_-]?key)\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|(?:Bearer\s+)?\S+)")


class RuntimeLog:
    def __init__(self, home: Path, interval: float = INTERVAL):
        self.home = home
        self.path = home / '.local/state/panel-de-control/lsfg-vk/runtime.log'
        self.interval = interval
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._error = None
        self._trims = 0

    def _open(self, *, create=False, writable=False):
        owner = self.home.stat()
        directory = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for name in self.path.parent.relative_to(self.home).parts:
                if create:
                    try:
                        os.mkdir(name, 0o700, dir_fd=directory)
                        if os.geteuid() == 0:
                            os.chown(name, owner.st_uid, owner.st_gid, dir_fd=directory, follow_symlinks=False)
                    except FileExistsError:
                        pass
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            flags = (os.O_RDWR if writable else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK
            if create:
                flags |= os.O_CREAT
            fd = os.open(self.path.name, flags, 0o600, dir_fd=directory)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid not in (owner.st_uid, os.geteuid()):
                os.close(fd)
                raise OSError('unsafe_log')
            if create:
                os.fchmod(fd, 0o600)
                if os.geteuid() == 0:
                    os.fchown(fd, owner.st_uid, owner.st_gid)
            return fd
        finally:
            os.close(directory)

    def prepare(self) -> bool:
        try:
            with self._lock:
                os.close(self._open(create=True, writable=True))
            self.maintain()
            return True
        except OSError:
            self._error = 'log_unavailable'
            return False

    def maintain(self):
        try:
            with self._lock, os.fdopen(self._open(writable=True), 'r+b') as handle:
                size = os.fstat(handle.fileno()).st_size
                if size > MAX_BYTES:
                    handle.seek(size - RETAIN_BYTES)
                    tail = handle.read(RETAIN_BYTES).partition(b"\n")[2]
                    handle.seek(0)
                    handle.write(tail)
                    handle.truncate(len(tail))
                    self._trims += 1
                self._error = None
        except OSError:
            self._error = 'log_unavailable'

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        with self._lock:
            if self._stop.is_set() or (self._thread and self._thread.is_alive()):
                return
            self._thread = threading.Thread(target=self._run, name='lsfg-log-retention', daemon=True)
            self._thread.start()

    def _run(self):
        while not self._stop.wait(self.interval):
            self.maintain()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def report(self) -> dict:
        from pdc_report.collector import redact_text

        result = {'available': False, 'scope': 'engine', 'generation_confirmed': None,
                  'retention_bytes': MAX_BYTES, 'retention_interval_seconds': self.interval,
                  'retention_scope': 'while_service_running', 'timestamp_source': 'file_mtime_not_activity',
                  'monitor_running': self.running,
                  'trims': self._trims, 'lines': []}
        try:
            with self._lock, os.fdopen(self._open(), 'rb') as handle:
                info = os.fstat(handle.fileno())
                handle.seek(max(0, info.st_size - REPORT_BYTES))
                data = handle.read(REPORT_BYTES)
                if info.st_size > REPORT_BYTES:
                    data = data.partition(b"\n")[2]
                content = data.decode('utf-8', 'replace')
            clean = redact_text(content, home=str(self.home))
            clean = _SECRET.sub(lambda match: match.group(1) + '=[redacted]', clean)
            clean = re.sub(r'''["'](?:/|[A-Za-z]:[\\/])[^"']*["']''', '[path]', clean)
            clean = re.sub(r'''(?<![A-Za-z0-9])(?:/|[A-Za-z]:[\\/])[^\s"'<>]+''', '[path]', clean)
            result.update(available=True, bytes=info.st_size, modified=info.st_mtime,
                          truncated=info.st_size > REPORT_BYTES,
                          lines=[line[:300] for line in clean.replace('\x00', '').splitlines()[-60:]])
        except OSError:
            result['reason'] = 'log_unavailable'
        if self._error:
            result['retention_error'] = self._error
        return result
