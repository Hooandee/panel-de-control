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

    @staticmethod
    def _current(name, control):
        return control.active() if name == "cores" else control.enabled()

    def _set_changed(self, name, control, target, completed):
        if not self._supported(control) or target is None:
            return True
        if self._current(name, control) == target:
            return True
        if name not in completed:
            completed.append(name)
        return control.set(target)

    def _snapshot(self):
        diagnostics = (
            self._frequency.diagnostics()
            if self._supported(self._frequency)
            else {}
        )
        requested = diagnostics.get("requested")
        return {
            "cores": self._cores.active() if self._supported(self._cores) else None,
            "smt": self._smt.enabled() if self._supported(self._smt) else None,
            "boost": self._boost.enabled() if self._supported(self._boost) else None,
            "frequency": (
                tuple(requested)
                if isinstance(requested, (list, tuple)) and len(requested) == 2
                else None
            ),
        }

    def _rollback(self, completed, snapshot):
        ok = True
        completed = set(completed)
        if "frequency" in completed:
            if (
                self._supported(self._smt)
                and not self._smt.enabled()
                and not self._smt.set(True)
            ):
                ok = False
            if (
                self._supported(self._cores)
                and self._cores.max_cores is not None
                and self._cores.active() != self._cores.max_cores
                and not self._cores.set(self._cores.max_cores)
            ):
                ok = False
            previous = snapshot.get("frequency")
            restored_frequency = (
                self._frequency.set_window(*previous)
                if previous is not None
                else self._frequency.set_auto()
            )
            safe_auto_noop = (
                previous is None
                and restored_frequency.status == "unverifiable"
                and restored_frequency.reason == "baseline_unavailable"
            )
            if not restored_frequency.ok and not safe_auto_noop:
                ok = False
        if "boost" in completed and not self._boost.set(snapshot["boost"]):
            ok = False
        if "smt" in completed and not self._smt.set(snapshot["smt"]):
            ok = False
        if "cores" in completed and not self._cores.set(snapshot["cores"]):
            ok = False
        return {"attempted": bool(completed), "ok": ok if completed else None}

    def _release_all(self, generation, preserve_frequency_ownership=False):
        failures = []
        error_type = None
        completed = []
        for name, control, target in (
            ("smt", self._smt, True),
            ("cores", self._cores, getattr(self._cores, "max_cores", None)),
            ("boost", self._boost, True),
        ):
            try:
                if not self._set_changed(name, control, target, completed):
                    failures.append(f"{name}_write_failed")
            except Exception as error:  # noqa: BLE001
                failures.append(f"{name}_write_failed")
                error_type = error_type or type(error).__name__

        frequency_status = None
        if self._supported(self._frequency):
            try:
                result = (
                    self._frequency.set_auto(preserve_ownership=True)
                    if preserve_frequency_ownership
                    else self._frequency.set_auto()
                )
                frequency_status = result.status
                safe_auto_noop = (
                    result.status == "unverifiable"
                    and result.reason == "baseline_unavailable"
                )
                if not result.ok and not safe_auto_noop:
                    failures.append(
                        f"frequency_{result.reason or 'apply_failed'}"
                    )
            except Exception as error:  # noqa: BLE001
                failures.append("frequency_exception")
                error_type = error_type or type(error).__name__

        return CpuCoordinatorResult(
            not failures,
            "partial" if failures else "applied",
            generation,
            {"attempted": False, "ok": None},
            failures[0] if failures else None,
            error_type,
            frequency_status,
        )

    def apply(
        self, intent, generation, enabled=True, eco=False,
        preserve_frequency_ownership=False,
    ):
        if not enabled:
            return self._release_all(
                generation,
                preserve_frequency_ownership=preserve_frequency_ownership,
            )
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
            frequency = intent.get("frequency") or {}
            frequency_supported = self._supported(self._frequency)

            if frequency_supported:
                if not self._set_changed(
                    "smt", self._smt, True, completed
                ):
                    rollback = self._rollback(completed, snapshot)
                    return CpuCoordinatorResult(
                        False,
                        "failed" if rollback["ok"] is not False else "partial",
                        generation,
                        rollback,
                        "smt_online_write_failed",
                    )
                if not self._set_changed(
                    "cores", self._cores,
                    getattr(self._cores, "max_cores", None), completed,
                ):
                    rollback = self._rollback(completed, snapshot)
                    return CpuCoordinatorResult(
                        False,
                        "failed" if rollback["ok"] is not False else "partial",
                        generation,
                        rollback,
                        "cores_online_write_failed",
                    )
                if not self._set_changed(
                    "boost", self._boost, targets["boost"], completed
                ):
                    rollback = self._rollback(completed, snapshot)
                    return CpuCoordinatorResult(
                        False,
                        "failed" if rollback["ok"] is not False else "partial",
                        generation,
                        rollback,
                        "boost_write_failed",
                    )

                if frequency.get("manual"):
                    freq_result = self._frequency.set_window(
                        frequency.get("min_khz"), frequency.get("max_khz")
                    )
                else:
                    freq_result = self._frequency.set_auto()
                frequency_status = freq_result.status
                safe_auto_noop = (
                    not frequency.get("manual")
                    and freq_result.status == "unverifiable"
                    and freq_result.reason == "baseline_unavailable"
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
                if freq_result.ok:
                    completed.append("frequency")

                for name, control in (
                    ("smt", self._smt),
                    ("cores", self._cores),
                ):
                    if not self._set_changed(
                        name, control, targets[name], completed
                    ):
                        rollback = self._rollback(completed, snapshot)
                        return CpuCoordinatorResult(
                            False,
                            "failed" if rollback["ok"] is not False else "partial",
                            generation,
                            rollback,
                            f"{name}_write_failed",
                            frequency_status=frequency_status,
                        )
            else:
                for name, control in (
                    ("cores", self._cores),
                    ("smt", self._smt),
                    ("boost", self._boost),
                ):
                    if not self._set_changed(
                        name, control, targets[name], completed
                    ):
                        rollback = self._rollback(completed, snapshot)
                        return CpuCoordinatorResult(
                            False,
                            "failed" if rollback["ok"] is not False else "partial",
                            generation,
                            rollback,
                            f"{name}_write_failed",
                        )

            return CpuCoordinatorResult(
                True,
                "clamped" if frequency_status == "clamped" else "applied",
                generation,
                {"attempted": False, "ok": None},
                frequency_status=frequency_status,
            )
        except Exception as error:  # noqa: BLE001
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
