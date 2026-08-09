import os


class DesktopCpuPolicy:
    """Readback-verified ACPI platform profile used when CPU watts are unavailable."""

    _REQUIRED = {"low-power", "balanced", "performance"}

    def __init__(self, root: str = "/") -> None:
        base = os.path.join(root, "sys/firmware/acpi")
        self._profile = os.path.join(base, "platform_profile")
        self._choices = os.path.join(base, "platform_profile_choices")
        self._original = None

    def _read(self, path):
        try:
            with open(path) as handle:
                return handle.read().strip()
        except OSError:
            return None

    @property
    def supported(self) -> bool:
        choices = set((self._read(self._choices) or "").split())
        return os.path.exists(self._profile) and self._REQUIRED.issubset(choices)

    def state(self):
        return self._read(self._profile) if self.supported else None

    def set(self, mode: str) -> dict:
        if not self.supported or mode not in self._REQUIRED:
            return {"ok": False, "applied": self.state(), "detail": "CPU platform profile unavailable"}
        before = self.state()
        if self._original is None:
            self._original = before
        try:
            with open(self._profile, "w") as handle:
                handle.write(mode)
        except OSError:
            return {"ok": False, "applied": self.state(), "detail": "CPU platform profile write failed"}
        applied = self.state()
        return {"ok": applied == mode, "applied": applied,
                "detail": "applied" if applied == mode else "CPU platform profile readback mismatch"}

    def restore(self, target=None) -> dict:
        if target is None and self._original is None:
            return {"ok": True, "applied": self.state(), "detail": "already free"}
        target = self._original if target is None else target
        choices = set((self._read(self._choices) or "").split())
        if target not in choices:
            return {"ok": False, "applied": self.state(),
                    "detail": "CPU platform profile restore target invalid"}
        try:
            with open(self._profile, "w") as handle:
                handle.write(target)
        except OSError:
            return {"ok": False, "applied": self.state(), "detail": "CPU platform profile restore failed"}
        applied = self.state()
        ok = applied == target
        if ok:
            self._original = None
        return {"ok": ok, "applied": applied,
                "detail": "restored" if ok else "CPU platform profile restore mismatch"}
