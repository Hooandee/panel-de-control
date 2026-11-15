import signal


DECK = 1000


class FakeProc:
    """A /proc tree on disk; signals either kill a process or are ignored by it."""

    def __init__(self, root):
        self.root = root
        self.signals = []
        self.ignores_term = set()
        self.ignores_kill = set()
        self.spawn_on_term = None

    def add(self, pid, ppid, name, argv=None, uid=DECK, state="S", start=None):
        base = self.root / str(pid)
        base.mkdir()
        (base / "stat").write_text(
            f"{pid} ({name}) {state} {ppid} " + " ".join(["0"] * 17) + f" {start or pid * 10} 0 0\n"
        )
        (base / "status").write_text(f"Name:\t{name}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
        (base / "cmdline").write_bytes(b"\0".join(part.encode() for part in (argv or [name])) + b"\0")
        return self

    def remove(self, pid):
        base = self.root / str(pid)
        for child in base.iterdir():
            child.unlink()
        base.rmdir()

    def kill(self, pid, signum):
        self.signals.append((pid, signum))
        if signum == signal.SIGTERM and self.spawn_on_term:
            spawn, self.spawn_on_term = self.spawn_on_term, None
            spawn()
        ignored = self.ignores_term if signum == signal.SIGTERM else self.ignores_kill
        if pid not in ignored:
            self.remove(pid)
