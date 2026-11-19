"""Respect independently parked CPUs on the GPD Win 5."""
from contextlib import contextmanager
from dataclasses import replace
import fcntl
import json
from pathlib import Path

import journal
from cpu.controls import CoreControl
from cpu.coordinator import CpuCoordinator, CpuCoordinatorResult
from cpu.frequency import _parse_cpu_list
from json_store import atomic_json_save
from sysfs import read_int, read_str, write_str


def is_gpd_win5(root):
    dmi = Path(root) / "sys/class/dmi/id"
    return (read_str(dmi / "sys_vendor"), read_str(dmi / "product_name")) == ("GPD", "G1618-05")


def select_core_control(root="/"):
    if is_gpd_win5(root):
        return GpdWin5Cores(root)
    return CoreControl(root)


class GpdWin5Cores:
    def __init__(self, root="/"):
        self.base = Path(root) / "sys/devices/system/cpu"
        self.runtime = Path(root) / "run/panel-de-control-gpd-cpu"
        self.groups = ()
        self.max_cores = None
        self.supported = False
        try:
            with self.transaction(blocking=False):
                pass
        except (OSError, ValueError, TypeError, KeyError):
            pass

    @contextmanager
    def transaction(self, blocking=True):
        self.runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (self.runtime / "lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                self.state = json.loads((self.runtime / "state.json").read_text())
            except FileNotFoundError:
                self.state = {}
            if not isinstance(self.state, dict):
                raise ValueError("invalid CPU ownership state")
            self._discover()
            self._reconcile_pending()
            yield

    def _save(self):
        atomic_json_save(str(self.runtime / "state.json"), self.state)

    def _reconcile_pending(self):
        pending = self.state.get("pending")
        if pending is None:
            return
        index = pending["index"]
        if index == "smt":
            if self._offline() != pending["before"] or read_str(self.base / "smt/control") == pending["after"]:
                self.state.pop("smt_offline", None)
                self.state["smt_uncertain"] = True
        elif self._online(index) == pending["value"]:
            # A crash between write and acknowledgement leaves the before/after
            # ambiguous when another service can park the same CPU. Keep it parked.
            if pending["value"] == 1:
                self._mark("owned", index, False)
            else:
                self._mark("uncertain", index, True)
        elif pending["value"] == 1:
            self._mark("failed", index, True)
        self.state.pop("pending")
        self._save()

    def _discover(self):
        present = set(_parse_cpu_list(read_str(self.base / "present")))
        known = self.state.get("core_ids", {})
        observed = {int(i): cid for i, cid in known.items() if int(i) in present}
        if set(observed) != present:
            for index in sorted(present):
                topology = self.base / f"cpu{index}/topology"
                cid = read_int(topology / "core_id")
                if cid is None:
                    continue
                siblings = _parse_cpu_list(read_str(topology / "core_cpus_list"))
                for i in ({index, *siblings} & present):
                    observed[i] = cid
            saved = {str(i): cid for i, cid in observed.items()}
            if saved != known:
                self.state["core_ids"] = saved
                self._save()
        by_core = {}
        if present and set(observed) == present:
            for i in sorted(present):
                by_core.setdefault(observed[i], []).append(i)
        self.groups = sorted(by_core.values(), key=min)
        self.max_cores = len(self.groups) or None
        self.supported = bool(self.max_cores and self.max_cores > 1)

    def _online(self, i):
        return 1 if i == 0 else read_int(self.base / f"cpu{i}/online")

    def active(self):
        return sum(any(self._online(i) == 1 for i in group) for group in self.groups)

    def _mark(self, field, index, enabled):
        values = set(self.state.get(field, ()))
        if enabled:
            values.add(index)
        else:
            values.discard(index)
        self.state[field] = sorted(values)

    def _change(self, index, value, after_owned, changes, manual=False):
        before = self._online(index)
        was_owned = index in self.state.get("owned", ())
        if before == value:
            if value and was_owned:
                self._mark("owned", index, False)
                self._save()
            return True
        if before not in (0, 1) or index == 0:
            return False
        if value and not manual and index in self.state.get("failed", ()):
            return False
        path = self.base / f"cpu{index}/online"
        self.state["pending"] = {"index": index, "value": value}
        self._save()
        if journal.active is not None:
            journal.active.write("INFO", "cpu", "hotplug_request", cpu=index, before=before,
                                 requested=value, owned=was_owned, manual=manual)
        written = write_str(str(path), value)
        observed = self._online(index)
        self.state.pop("pending", None)
        if observed != value:
            self._mark("failed", index, bool(value))
            self._save()
            return False
        changes.append((index, before, was_owned))
        self._mark("owned", index, after_owned)
        self._mark("failed", index, False)
        self._mark("uncertain", index, False)
        self._save()
        return written

    def _offline(self):
        present = _parse_cpu_list(read_str(self.base / "present"))
        values = {i: self._online(i) for i in present}
        if not values or None in values.values():
            return None
        return sorted(i for i, value in values.items() if value == 0)

    def _smt(self, enabled, manual, changes, rollback_off=False):
        path = self.base / "smt/control"
        current = read_str(path)
        target = "on" if enabled else "off"
        owned = self.state.get("smt_offline")
        if self.state.get("smt_uncertain"):
            if not manual:
                return False
            self.state.pop("smt_uncertain")
            self._save()
        if current == target:
            if enabled and owned is not None:
                self.state.pop("smt_offline")
                self._save()
            return True
        if current not in ("on", "off"):
            return not manual
        # The global SMT switch can bring back CPUs disabled independently.
        # Only reverse our own switch against its verified post-write mask.
        offline = self._offline()
        if enabled and owned is None:
            if not manual:
                return True
            if not self.groups:
                return False
            expected = sorted(i for group in self.groups for i in group[1:])
        else:
            expected = owned if enabled else []
        if offline is None or not self.groups:
            return False
        siblings = sorted(i for group in self.groups for i in group[1:])
        if rollback_off:
            if not set(offline).issubset(siblings):
                return False
        elif offline != expected:
            return False
        self.state["pending"] = {"index": "smt", "before": offline, "after": target, "siblings": siblings}
        self._save()
        written = write_str(str(path), target)
        actual = read_str(path)
        observed = self._offline()
        if actual != current:
            changes.append(("smt", current, owned))
        if observed is not None:
            for i in sorted((set(offline) ^ set(observed)) & set(siblings)):
                if actual == current:
                    changes.append((i, int(i not in offline), i in self.state.get("owned", ())))
        self._record_smt_result(offline, target, siblings)
        self.state.pop("pending", None)
        self._save()
        return written and actual == target and observed == ([] if enabled else siblings)

    def _record_smt_result(self, before, target, siblings):
        current = read_str(self.base / "smt/control")
        observed = self._offline()
        if current == "off" and target == "off":
            self.state["smt_offline"] = siblings
            for i in siblings:
                self._mark("owned", i, False)
                self._mark("failed", i, False)
        if current == "on" and observed is not None:
            previously_owned = self.state.pop("smt_offline", ())
            for i in siblings:
                if i in observed and (i in previously_owned or i not in before):
                    self._mark("owned", i, True)
                    if target == "on":
                        self._mark("failed", i, True)

    def _release_cores(self, changes):
        ok = True
        for index in list(self.state.get("owned", ())):
            if read_str(self.base / "smt/control") == "off" and not any(
                group[0] == index for group in self.groups
            ):
                ok = False
            elif not self._change(index, 1, False, changes):
                ok = False
        return ok

    def release(self):
        return self._release_cores([]) and self._smt(True, False, []) and not self.state.get("uncertain")

    def apply_profile(self, profile, manual, changes, is_current=lambda: True):
        smt = bool(profile.get("smt", True))
        current_smt = read_str(self.base / "smt/control")
        if self.state.get("smt_uncertain") and manual != "smt":
            return "smt_ownership_uncertain"
        if current_smt in ("on", "off") and (smt != (current_smt == "on") or self.state.get("smt_uncertain")):
            if not self._release_cores(changes) or not self._smt(smt, manual == "smt", changes):
                return "smt_write_failed"
        if not self.supported:
            return "topology_unavailable" if manual == "cores" else None
        requested = profile.get("cores")
        limit = self.max_cores if requested is None else max(1, min(self.max_cores, requested))
        for pos, group in enumerate(self.groups):
            if not is_current():
                return "stale_generation"
            wanted = int(pos < limit)
            for index in group:
                before = self._online(index)
                owned = index in self.state.get("owned", ())
                if before == 1 and index in self.state.get("uncertain", ()):
                    self._mark("uncertain", index, False)
                    self._save()
                if before == 1 and owned:
                    self._mark("owned", index, False)
                    self._save()
                    owned = False
                if before == wanted:
                    continue
                if wanted and not owned:
                    if manual != "cores":
                        continue
                    if read_str(self.base / "smt/control") == "off" and index != group[0]:
                        continue
                if not self._change(index, wanted, not wanted, changes, manual == "cores"):
                    return "cores_write_failed"
        return None

    def rollback(self, changes):
        ok = True
        for index, before, was_owned in reversed(changes):
            if index == "smt":
                restored = self._smt(before == "on", True, [], rollback_off=before == "off")
                if restored and before == "off" and was_owned is None:
                    self.state.pop("smt_offline", None)
                    self._save()
                ok = restored and ok
            else:
                try:
                    restored = self._change(index, before, was_owned, [])
                except OSError:
                    restored = False
                ok = restored and ok
        return ok


class GpdWin5Coordinator(CpuCoordinator):
    def __init__(self, cores, smt, boost, frequency):
        super().__init__(None, None, boost, frequency)
        self.topology = cores

    def apply(self, intent, generation, enabled=True, is_current=lambda: True, **kwargs):
        try:
            with self.topology.transaction():
                if not is_current():
                    return CpuCoordinatorResult(False, "rejected", generation,
                                                {"attempted": False, "ok": None}, "stale_generation")
                if not enabled:
                    released = self.topology.release()
                    result = super().apply(intent, generation, enabled=False, **kwargs)
                    if not released:
                        return replace(result, ok=False, status="partial", error_code="topology_release_failed")
                    return result
                return self._apply_locked(intent, generation, is_current, kwargs)
        except (OSError, ValueError, TypeError, KeyError) as error:
            return CpuCoordinatorResult(False, "failed", generation, {"attempted": False, "ok": None},
                                        "topology_state_unavailable", type(error).__name__)

    def _apply_locked(self, intent, generation, is_current, kwargs):
        changes = []
        try:
            failure = self.topology.apply_profile(intent, intent.get("_manual_topology"), changes, is_current)
            if failure:
                result = CpuCoordinatorResult(False, "failed", generation, {"attempted": False, "ok": None}, failure)
            else:
                result = super().apply(intent, generation, **kwargs)
            if result.ok and not is_current():
                result = replace(result, ok=False, status="rejected", error_code="stale_generation")
            if result.ok and intent.get("_persist_topology") is not None:
                try:
                    intent["_persist_topology"]()
                except Exception as error:
                    result = replace(result, ok=False, status="failed", error_code="store_write_failed",
                                     error_type=type(error).__name__)
        except OSError as error:
            result = CpuCoordinatorResult(False, "failed", generation, {"attempted": False, "ok": None},
                                          "topology_state_unavailable", type(error).__name__)
        if not result.ok and changes:
            try:
                ok = self.topology.rollback(changes) and result.rollback.get("ok") is not False
            except OSError:
                ok = False
            return replace(result, status="failed" if ok else "partial", rollback={"attempted": True, "ok": ok})
        target = intent.get("cores") or self.topology.max_cores
        if result.ok and target is not None and self.topology.active() < target:
            return replace(result, status="clamped")
        return result
