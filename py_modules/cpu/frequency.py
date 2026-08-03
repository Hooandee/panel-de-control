"""Capability-driven Linux cpufreq window control."""

from dataclasses import dataclass
import glob
import os
import re
import time

from sysfs import read_int, read_str, write_str


_CPUFREQ = "sys/devices/system/cpu/cpufreq"
_POLICY_NAME = re.compile(r"policy([0-9]+)$")


def _parse_cpu_list(value):
    cpus = []
    for part in (value or "").replace(",", " ").split():
        try:
            if "-" in part:
                start, end = (int(item) for item in part.split("-", 1))
                if start > end:
                    return ()
                cpus.extend(range(start, end + 1))
            else:
                cpus.append(int(part))
        except ValueError:
            return ()
    return tuple(sorted(set(cpus)))


@dataclass(frozen=True)
class Policy:
    name: str
    path: str
    driver: str | None
    cpus: tuple[int, ...]
    hardware_min_khz: int
    hardware_max_khz: int

    @property
    def scaling_min_path(self):
        return os.path.join(self.path, "scaling_min_freq")

    @property
    def scaling_max_path(self):
        return os.path.join(self.path, "scaling_max_freq")

    def read_window(self):
        minimum = read_int(self.scaling_min_path)
        maximum = read_int(self.scaling_max_path)
        if minimum is None or maximum is None or minimum > maximum:
            return None
        return minimum, maximum


@dataclass(frozen=True)
class CpuFrequencyResult:
    ok: bool
    status: str
    requested: tuple[int, int] | None
    applied: tuple[int, int] | None
    rollback: dict
    reason: str | None
    epoch: int


class NullCpuFrequency:
    supported = False
    backend = "unsupported"

    def __init__(self, reason="no_policies"):
        self._reason = reason

    def get_range(self):
        return None

    def get_window(self):
        return None

    def set_window(self, minimum_khz, maximum_khz):
        return CpuFrequencyResult(
            False, "unsupported", (minimum_khz, maximum_khz), None,
            {"attempted": False, "ok": None}, self._reason, 0,
        )

    def set_auto(self):
        return CpuFrequencyResult(
            False, "unsupported", None, None,
            {"attempted": False, "ok": None}, self._reason, 0,
        )

    def diagnostics(self):
        return {
            "supported": False,
            "backend": self.backend,
            "reason": self._reason,
            "policies": [],
            "drivers": [],
            "policy_state": [],
        }


class LinuxCpuFrequency:
    supported = True
    backend = "linux_cpufreq"

    def __init__(self, root, policies):
        self._root = root
        self._policies = tuple(policies)
        self._fingerprint = self._make_fingerprint(self._policies)
        self._baseline = None
        self._requested = None
        self._epoch = 0

    @staticmethod
    def _policy_identity(policy):
        return (
            policy.name,
            os.path.realpath(policy.path),
            policy.cpus,
            policy.hardware_min_khz,
            policy.hardware_max_khz,
        )

    @staticmethod
    def _make_fingerprint(policies):
        return tuple(
            LinuxCpuFrequency._policy_identity(policy) for policy in policies
        )

    def _refresh(self):
        policies, reason = _discover_policies(self._root)
        if policies is None:
            return reason
        fingerprint = self._make_fingerprint(policies)
        if fingerprint != self._fingerprint:
            self._policies = tuple(policies)
            self._fingerprint = fingerprint
            self._epoch += 1
        return None

    def get_range(self):
        return (
            min(policy.hardware_min_khz for policy in self._policies),
            max(policy.hardware_max_khz for policy in self._policies),
        )

    def get_window(self):
        if self._refresh() is not None:
            return None
        windows = [policy.read_window() for policy in self._policies]
        if any(window is None for window in windows):
            return None
        return min(window[0] for window in windows), max(window[1] for window in windows)

    @staticmethod
    def _target_for(policy, requested):
        minimum = min(max(requested[0], policy.hardware_min_khz), policy.hardware_max_khz)
        maximum = min(max(requested[1], policy.hardware_min_khz), policy.hardware_max_khz)
        return minimum, maximum

    @staticmethod
    def _ordered_writes(policy, current, target):
        if target[0] > current[1]:
            return (
                (policy.scaling_max_path, target[1]),
                (policy.scaling_min_path, target[0]),
            )
        return (
            (policy.scaling_min_path, target[0]),
            (policy.scaling_max_path, target[1]),
        )

    def _apply_pair(self, policy, current, target):
        for attempt in range(2):
            for path, value in self._ordered_writes(policy, current, target):
                if not write_str(path, f"{value}\n"):
                    return "write_failed"
            applied = policy.read_window()
            if applied == target:
                return None
            if applied is None:
                return "readback_mismatch"
            current = applied
            if attempt == 0:
                time.sleep(0.05)
        return "readback_mismatch"

    def _restore_pair(self, policy, target):
        current = policy.read_window()
        if current is None:
            return False
        for attempt in range(2):
            for path, value in self._ordered_writes(policy, current, target):
                write_str(path, f"{value}\n")
            applied = policy.read_window()
            if applied == target:
                return True
            if applied is None:
                return False
            current = applied
            if attempt == 0:
                time.sleep(0.05)
        return False

    def _rollback(self, touched, snapshots):
        ok = True
        for policy in reversed(touched):
            if not self._restore_pair(policy, snapshots[policy.name]):
                ok = False
        return {"attempted": bool(touched), "ok": ok if touched else None}

    def _result(self, ok, status, requested, rollback, reason=None):
        windows = [policy.read_window() for policy in self._policies]
        applied = None
        if windows and all(window is not None for window in windows):
            applied = (
                min(window[0] for window in windows),
                max(window[1] for window in windows),
            )
        return CpuFrequencyResult(
            ok, status, requested, applied, rollback, reason, self._epoch,
        )

    def set_window(self, minimum_khz, maximum_khz):
        requested = (minimum_khz, maximum_khz)
        reason = self._refresh()
        if reason is not None:
            return self._result(
                False, "unsupported", requested,
                {"attempted": False, "ok": None}, reason,
            )
        if (
            isinstance(minimum_khz, bool)
            or isinstance(maximum_khz, bool)
            or not isinstance(minimum_khz, int)
            or not isinstance(maximum_khz, int)
        ):
            return self._result(
                False, "rejected", requested,
                {"attempted": False, "ok": None}, "invalid_range",
            )
        envelope = self.get_range()
        if (
            minimum_khz > maximum_khz
            or minimum_khz < envelope[0]
            or maximum_khz > envelope[1]
        ):
            return self._result(
                False, "rejected", requested,
                {"attempted": False, "ok": None}, "invalid_range",
            )
        if self._baseline is not None:
            baseline_names = {identity[0] for identity in self._baseline}
            identity_changed = any(
                policy.name in baseline_names
                and self._policy_identity(policy) not in self._baseline
                for policy in self._policies
            )
            if identity_changed:
                return self._result(
                    False, "rejected", requested,
                    {"attempted": False, "ok": None},
                    "policy_identity_changed",
                )

        snapshots = {}
        targets = {}
        for policy in self._policies:
            current = policy.read_window()
            if current is None:
                return self._result(
                    False, "failed", requested,
                    {"attempted": False, "ok": None}, "read_failed",
                )
            snapshots[policy.name] = current
            targets[policy.name] = self._target_for(policy, requested)
        baseline_entries = {
            self._policy_identity(policy): snapshots[policy.name]
            for policy in self._policies
        }

        touched = []
        for policy in self._policies:
            touched.append(policy)
            failure = self._apply_pair(
                policy, snapshots[policy.name], targets[policy.name]
            )
            if failure is not None:
                rollback = self._rollback(touched, snapshots)
                if not rollback["ok"] and self._baseline is None:
                    self._baseline = baseline_entries
                return self._result(
                    False, "failed" if rollback["ok"] else "partial",
                    requested, rollback, failure,
                )

        if self._baseline is None:
            self._baseline = baseline_entries
        else:
            for identity, window in baseline_entries.items():
                self._baseline.setdefault(identity, window)
        self._requested = requested
        clamped = any(target != requested for target in targets.values())
        return self._result(
            True, "clamped" if clamped else "applied", requested,
            {"attempted": False, "ok": None},
        )

    def set_auto(self):
        reason = self._refresh()
        if reason is not None:
            return self._result(
                False, "unsupported", None,
                {"attempted": False, "ok": None}, reason,
            )
        if self._baseline is None:
            return self._result(
                False, "unverifiable", None,
                {"attempted": False, "ok": None}, "baseline_unavailable",
            )
        current_identities = {
            self._policy_identity(policy) for policy in self._policies
        }
        if set(self._baseline) != current_identities:
            return self._result(
                False, "unverifiable", None,
                {"attempted": False, "ok": None}, "baseline_stale",
            )
        touched = []
        restored = True
        for policy in self._policies:
            touched.append(policy)
            identity = self._policy_identity(policy)
            if not self._restore_pair(policy, self._baseline[identity]):
                restored = False
        if not restored:
            return self._result(
                False, "partial", None,
                {"attempted": True, "ok": False}, "restore_failed",
            )
        self._baseline = None
        self._requested = None
        return self._result(
            True, "restored", None, {"attempted": True, "ok": True},
        )

    def diagnostics(self):
        refresh_reason = self._refresh()
        policy_state = []
        for policy in self._policies:
            window = policy.read_window()
            policy_state.append({
                "name": policy.name,
                "cpus": list(policy.cpus),
                "driver": policy.driver,
                "hardware_min_khz": policy.hardware_min_khz,
                "hardware_max_khz": policy.hardware_max_khz,
                "applied_min_khz": window[0] if window else None,
                "applied_max_khz": window[1] if window else None,
            })
        return {
            "supported": True,
            "backend": self.backend,
            "reason": refresh_reason,
            "epoch": self._epoch,
            "requested": list(self._requested) if self._requested else None,
            "owned": self._baseline is not None,
            "policies": [policy.name for policy in self._policies],
            "drivers": sorted({policy.driver for policy in self._policies if policy.driver}),
            "policy_state": policy_state,
        }


def _discover_policies(root):
    base = os.path.join(root, _CPUFREQ)
    candidates = []
    seen = set()
    for path in glob.glob(os.path.join(base, "policy*")):
        match = _POLICY_NAME.fullmatch(os.path.basename(path))
        if not match:
            continue
        resolved = os.path.realpath(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        candidates.append((int(match.group(1)), path))

    policies = []
    for _, path in sorted(candidates):
        scaling_paths = (
            os.path.join(path, "scaling_min_freq"),
            os.path.join(path, "scaling_max_freq"),
        )
        values = {
            "current_min": read_int(scaling_paths[0]),
            "current_max": read_int(scaling_paths[1]),
            "hardware_min": read_int(os.path.join(path, "cpuinfo_min_freq")),
            "hardware_max": read_int(os.path.join(path, "cpuinfo_max_freq")),
        }
        if any(value is None for value in values.values()):
            return None, "incomplete_policy"
        if not all(os.access(node, os.W_OK) for node in scaling_paths):
            return None, "unwritable_policy"
        if (
            values["hardware_min"] > values["hardware_max"]
            or values["current_min"] > values["current_max"]
        ):
            return None, "invalid_bounds"
        cpu_text = read_str(os.path.join(path, "related_cpus"))
        if cpu_text is None:
            cpu_text = read_str(os.path.join(path, "affected_cpus"))
        policies.append(Policy(
            name=os.path.basename(path),
            path=path,
            driver=read_str(os.path.join(path, "scaling_driver")),
            cpus=_parse_cpu_list(cpu_text),
            hardware_min_khz=values["hardware_min"],
            hardware_max_khz=values["hardware_max"],
        ))
    if not policies:
        return None, "no_policies"
    return policies, None


def select_cpu_frequency(root="/"):
    policies, reason = _discover_policies(root)
    if policies is None:
        return NullCpuFrequency(reason)
    return LinuxCpuFrequency(root, policies)
