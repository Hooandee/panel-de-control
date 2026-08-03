"""Serialized transaction for all CPU controls."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CpuCoordinatorResult:
    ok: bool
    status: str
    generation: int
    rollback: dict
    error_code: str | None = None
    error_type: str | None = None
    frequency_status: str | None = None


class CpuCoordinator:
    def __init__(self, cores, smt, boost, frequency):
        self._cores = cores
        self._smt = smt
        self._boost = boost
        self._frequency = frequency

    @staticmethod
    def _supported(control):
        return bool(getattr(control, "supported", False))

    def _snapshot(self):
        return {
            "cores": self._cores.active() if self._supported(self._cores) else None,
            "smt": self._smt.enabled() if self._supported(self._smt) else None,
            "boost": self._boost.enabled() if self._supported(self._boost) else None,
        }

    def _rollback(self, completed, snapshot):
        ok = True
        for name in reversed(completed):
            if name == "cores":
                restored = self._cores.set(snapshot[name])
            elif name == "smt":
                restored = self._smt.set(snapshot[name])
            elif name == "boost":
                restored = self._boost.set(snapshot[name])
            else:
                continue
            if not restored:
                ok = False
        return {"attempted": bool(completed), "ok": ok if completed else None}

    def apply(self, intent, generation, enabled=True, eco=False):
        snapshot = self._snapshot()
        completed = []
        frequency_status = None
        try:
            targets = {
                "cores": (
                    intent.get("cores")
                    if intent.get("cores") is not None
                    else getattr(self._cores, "max_cores", None)
                ),
                "smt": bool(intent.get("smt", True)),
                "boost": False if eco else bool(intent.get("boost", True)),
            }
            if not enabled:
                targets = {
                    "cores": getattr(self._cores, "max_cores", None),
                    "smt": True,
                    "boost": True,
                }

            for name, control in (
                ("cores", self._cores),
                ("smt", self._smt),
                ("boost", self._boost),
            ):
                if not self._supported(control) or targets[name] is None:
                    continue
                if not control.set(targets[name]):
                    rollback = self._rollback(completed, snapshot)
                    return CpuCoordinatorResult(
                        False,
                        "failed" if rollback["ok"] is not False else "partial",
                        generation,
                        rollback,
                        f"{name}_write_failed",
                    )
                completed.append(name)

            if self._supported(self._frequency):
                frequency = intent.get("frequency") or {}
                if enabled and frequency.get("manual"):
                    freq_result = self._frequency.set_window(
                        frequency.get("min_khz"), frequency.get("max_khz")
                    )
                else:
                    freq_result = self._frequency.set_auto()
                frequency_status = freq_result.status
                safe_auto_noop = (
                    not (enabled and frequency.get("manual"))
                    and freq_result.status == "unverifiable"
                )
                if not freq_result.ok and not safe_auto_noop:
                    rollback = self._rollback(completed, snapshot)
                    return CpuCoordinatorResult(
                        False,
                        "partial" if rollback["ok"] is False or freq_result.status == "partial" else "failed",
                        generation,
                        rollback,
                        f"frequency_{freq_result.reason or 'apply_failed'}",
                        frequency_status=frequency_status,
                    )

            return CpuCoordinatorResult(
                True,
                "clamped" if frequency_status == "clamped" else "applied",
                generation,
                {"attempted": False, "ok": None},
                frequency_status=frequency_status,
            )
        except Exception as error:  # noqa: BLE001 - boundary around hardware backends
            rollback = self._rollback(completed, snapshot)
            return CpuCoordinatorResult(
                False,
                "failed" if rollback["ok"] is not False else "partial",
                generation,
                rollback,
                "exception",
                type(error).__name__,
                frequency_status,
            )
