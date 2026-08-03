"""Capability-driven Linux cpufreq window control."""

from dataclasses import dataclass
import glob
import os
import re
import time

from sysfs import read_int, read_str, write_str


_CPUFREQ = "sys/devices/system/cpu/cpufreq"
_POLICY_NAME = re.compile(r"policy([0-9]+)$")
_APPLIED_UNSET = object()


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
    related_cpus: tuple[int, ...]
    affected_cpus: tuple[int, ...]
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

    def set_auto(self, preserve_ownership=False):
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

    def __init__(
        self, root, policies, persisted_state=None, persist_state=None,
        boot_id=None,
    ):
        self._root = root
        self._policies = tuple(policies)
        self._fingerprint = self._make_fingerprint(self._policies)
        self._baseline = None
        self._requested = None
        self._epoch = 0
        self._persist_state = persist_state
        self._boot_id = boot_id or read_str(
            os.path.join(root, "proc/sys/kernel/random/boot_id")
        )
        self._durable_state_reason = None
        self._load_persisted_state(persisted_state)

    @staticmethod
    def _policy_identity(policy):
        return (
            policy.name,
            os.path.realpath(policy.path),
            policy.driver,
            policy.related_cpus,
            policy.hardware_min_khz,
            policy.hardware_max_khz,
        )

    @staticmethod
    def _make_fingerprint(policies):
        return tuple(
            (
                *LinuxCpuFrequency._policy_identity(policy),
                policy.affected_cpus,
            )
            for policy in policies
        )

    @staticmethod
    def _identity_payload(identity):
        return [
            identity[0],
            identity[1],
            identity[2],
            list(identity[3]),
            identity[4],
            identity[5],
        ]

    @staticmethod
    def _identity_from_payload(payload):
        if not isinstance(payload, list) or len(payload) != 6:
            return None
        name, path, driver, cpus, hardware_min, hardware_max = payload
        if (
            not isinstance(name, str)
            or not isinstance(path, str)
            or driver is not None and not isinstance(driver, str)
            or not isinstance(cpus, list)
            or any(not isinstance(cpu, int) for cpu in cpus)
            or not isinstance(hardware_min, int)
            or not isinstance(hardware_max, int)
            or hardware_min > hardware_max
        ):
            return None
        return (
            name, path, driver, tuple(cpus), hardware_min, hardware_max,
        )

    def _state_payload(
        self, baseline=_APPLIED_UNSET, requested=_APPLIED_UNSET
    ):
        owned = self._baseline if baseline is _APPLIED_UNSET else baseline
        active_request = (
            self._requested if requested is _APPLIED_UNSET else requested
        )
        if not owned:
            return None
        return {
            "version": 1,
            "boot_id": self._boot_id,
            "requested": list(active_request) if active_request else None,
            "baseline": [
                {
                    "identity": self._identity_payload(identity),
                    "window": list(window),
                }
                for identity, window in sorted(owned.items())
            ],
        }

    def _persist_ownership(
        self, baseline=_APPLIED_UNSET, requested=_APPLIED_UNSET
    ):
        if not callable(self._persist_state):
            return True
        try:
            self._persist_state(self._state_payload(baseline, requested))
            return True
        except Exception:  # noqa: BLE001
            self._durable_state_reason = "ownership_persist_failed"
            return False

    def _replace_ownership(self, baseline, requested):
        if not self._persist_ownership(baseline, requested):
            return False
        self._baseline = dict(baseline) if baseline else None
        self._requested = tuple(requested) if requested else None
        self._durable_state_reason = None
        return True

    def _load_persisted_state(self, state):
        if state is None:
            return
        if (
            not isinstance(state, dict)
            or state.get("version") != 1
            or not self._boot_id
            or state.get("boot_id") != self._boot_id
            or not isinstance(state.get("baseline"), list)
        ):
            self._durable_state_reason = "ownership_state_stale"
            if callable(self._persist_state):
                try:
                    self._persist_state(None)
                except Exception:  # noqa: BLE001
                    pass
            return
        baseline = {}
        for entry in state["baseline"]:
            if not isinstance(entry, dict):
                baseline = {}
                break
            identity = self._identity_from_payload(entry.get("identity"))
            window = entry.get("window")
            if (
                identity is None
                or identity in baseline
                or not isinstance(window, list)
                or len(window) != 2
                or any(not isinstance(value, int) for value in window)
                or window[0] > window[1]
                or window[0] < identity[4]
                or window[1] > identity[5]
            ):
                baseline = {}
                break
            baseline[identity] = tuple(window)
        requested = state.get("requested")
        if (
            not baseline
            or not isinstance(requested, list)
            or len(requested) != 2
            or any(not isinstance(value, int) for value in requested)
        ):
            self._durable_state_reason = "ownership_state_invalid"
            return
        self._baseline = baseline
        self._requested = tuple(requested)

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
                if not self._policy_is_current(policy):
                    return "policy_topology_changed"
                if not write_str(path, f"{value}\n"):
                    return "write_failed"
            applied = policy.read_window()
            if not self._policy_is_current(policy):
                return "policy_topology_changed"
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
        if current is None or not self._policy_is_current(policy):
            return False
        for attempt in range(2):
            for path, value in self._ordered_writes(policy, current, target):
                if not self._policy_is_current(policy):
                    return False
                write_str(path, f"{value}\n")
            applied = policy.read_window()
            if not self._policy_is_current(policy):
                return False
            if applied == target:
                return True
            if applied is None:
                return False
            current = applied
            if attempt == 0:
                time.sleep(0.05)
        return False

    def _rollback(self, touched, snapshots):
        policies, reason = _discover_policies(self._root)
        current = {
            self._policy_identity(policy): policy for policy in (policies or ())
        }
        ok = True
        for policy in reversed(touched):
            live = current.get(self._policy_identity(policy))
            if (
                reason is not None
                or live is None
                or not self._restore_pair(live, snapshots[policy.name])
            ):
                ok = False
        return {"attempted": bool(touched), "ok": ok if touched else None}

    def _rollback_matching_targets(self, touched, snapshots, targets):
        policies, reason = _discover_policies(self._root)
        current = {
            self._policy_identity(policy): policy for policy in (policies or ())
        }
        attempted = False
        ok = reason is None
        remaining = {}
        for policy in reversed(touched):
            identity = self._policy_identity(policy)
            live = current.get(identity)
            if live is None:
                continue
            window = live.read_window()
            if window == targets[policy.name] and window != snapshots[policy.name]:
                attempted = True
                if not self._restore_pair(live, snapshots[policy.name]):
                    ok = False
            if live.read_window() == targets[policy.name]:
                remaining[identity] = snapshots[policy.name]
        return {
            "rollback": {
                "attempted": attempted,
                "ok": ok if attempted else None,
            },
            "remaining": remaining,
        }

    def _policy_is_current(self, policy):
        policies, reason = _discover_policies(self._root)
        if reason is not None:
            return False
        for current in policies:
            if self._policy_identity(current) == self._policy_identity(policy):
                return current.affected_cpus == policy.affected_cpus
        return False

    @staticmethod
    def _aggregate_windows(windows):
        if not windows or any(window is None for window in windows):
            return None
        return (
            min(window[0] for window in windows),
            max(window[1] for window in windows),
        )

    def _result(
        self, ok, status, requested, rollback, reason=None,
        applied=_APPLIED_UNSET,
    ):
        if applied is _APPLIED_UNSET:
            applied = self._aggregate_windows(
                [policy.read_window() for policy in self._policies]
            )
        return CpuFrequencyResult(
            ok, status, requested, applied, rollback, reason, self._epoch,
        )

    def _verify_transaction(self, fingerprint, targets):
        refresh_reason = self._refresh()
        if refresh_reason is not None or self._fingerprint != fingerprint:
            return "policy_topology_changed", None
        windows = []
        for policy in self._policies:
            window = policy.read_window()
            windows.append(window)
            if window != targets.get(policy.name):
                return "readback_mismatch", self._aggregate_windows(windows)
        refresh_reason = self._refresh()
        if refresh_reason is not None or self._fingerprint != fingerprint:
            return "policy_topology_changed", self._aggregate_windows(windows)
        return None, self._aggregate_windows(windows)

    def set_window(self, minimum_khz, maximum_khz):
        requested = (minimum_khz, maximum_khz)
        reason = self._refresh()
        if reason is not None:
            return self._result(
                False, "unsupported", requested,
                {"attempted": False, "ok": None}, reason,
            )
        if callable(self._persist_state) and not self._boot_id:
            return self._result(
                False, "rejected", requested,
                {"attempted": False, "ok": None},
                "boot_id_unavailable",
            )
        if self._durable_state_reason == "ownership_state_invalid":
            return self._result(
                False, "rejected", requested,
                {"attempted": False, "ok": None},
                "ownership_state_invalid",
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
        transaction_fingerprint = self._fingerprint

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
        previous_baseline = (
            dict(self._baseline) if self._baseline is not None else None
        )
        previous_requested = self._requested
        owned_baseline = dict(previous_baseline or {})
        for identity, window in baseline_entries.items():
            owned_baseline.setdefault(identity, window)
        if not self._replace_ownership(owned_baseline, requested):
            return self._result(
                False, "failed", requested,
                {"attempted": False, "ok": None},
                "ownership_persist_failed",
            )

        touched = []
        for policy in self._policies:
            touched.append(policy)
            failure = self._apply_pair(
                policy, snapshots[policy.name], targets[policy.name]
            )
            if failure is not None:
                rollback = self._rollback(touched, snapshots)
                if rollback["ok"]:
                    self._replace_ownership(
                        previous_baseline, previous_requested
                    )
                return self._result(
                    False, "failed" if rollback["ok"] else "partial",
                    requested, rollback, failure,
                )

        verification_reason, applied = self._verify_transaction(
            transaction_fingerprint, targets
        )
        if verification_reason is not None:
            if verification_reason == "policy_topology_changed":
                rollback = self._rollback(touched, snapshots)
                remaining = {}
            else:
                selective = self._rollback_matching_targets(
                    touched, snapshots, targets
                )
                rollback = selective["rollback"]
                remaining = selective["remaining"]
            if rollback["ok"] and not remaining:
                self._replace_ownership(
                    previous_baseline, previous_requested
                )
            return self._result(
                False,
                "partial" if remaining or rollback["ok"] is False else "failed",
                requested,
                rollback,
                verification_reason,
                applied=applied,
            )

        clamped = any(target != requested for target in targets.values())
        return self._result(
            True, "clamped" if clamped else "applied", requested,
            {"attempted": False, "ok": None},
            applied=applied,
        )

    def set_auto(self, preserve_ownership=False):
        reason = self._refresh()
        if reason is not None:
            return self._result(
                False, "unsupported", None,
                {"attempted": False, "ok": None}, reason,
            )
        if self._baseline is None:
            return self._result(
                False, "unverifiable", None,
                {"attempted": False, "ok": None},
                (
                    "ownership_state_invalid"
                    if self._durable_state_reason == "ownership_state_invalid"
                    else "baseline_unavailable"
                ),
            )
        current_identities = {
            self._policy_identity(policy) for policy in self._policies
        }
        if set(self._baseline) != current_identities:
            matching = [
                policy
                for policy in self._policies
                if self._policy_identity(policy) in self._baseline
            ]
            restored = True
            remaining_baseline = dict(self._baseline)
            for policy in matching:
                identity = self._policy_identity(policy)
                if not self._restore_pair(policy, self._baseline[identity]):
                    restored = False
                else:
                    remaining_baseline.pop(identity, None)
            if not remaining_baseline:
                if (
                    not preserve_ownership
                    and not self._replace_ownership(None, None)
                ):
                    return self._result(
                        False, "partial", None,
                        {"attempted": bool(matching), "ok": restored},
                        "ownership_clear_failed",
                    )
                return self._result(
                    restored,
                    "restored" if restored else "partial",
                    None,
                    {"attempted": bool(matching), "ok": restored},
                    None if restored else "restore_failed",
                )
            if matching:
                if (
                    not preserve_ownership
                    and not self._replace_ownership(
                        remaining_baseline, self._requested
                    )
                ):
                    return self._result(
                        False, "partial", None,
                        {"attempted": True, "ok": restored},
                        "ownership_persist_failed",
                    )
                return self._result(
                    False,
                    "partial",
                    None,
                    {"attempted": True, "ok": restored},
                    "baseline_stale" if restored else "restore_failed",
                )
            return self._result(
                False, "unverifiable", None,
                {"attempted": False, "ok": None}, "baseline_stale",
            )
        touched = []
        restored = True
        transaction_fingerprint = self._fingerprint
        targets = {}
        for policy in self._policies:
            touched.append(policy)
            identity = self._policy_identity(policy)
            targets[policy.name] = self._baseline[identity]
            if not self._restore_pair(policy, targets[policy.name]):
                restored = False
        if not restored:
            return self._result(
                False, "partial", None,
                {"attempted": True, "ok": False}, "restore_failed",
            )
        verification_reason, applied = self._verify_transaction(
            transaction_fingerprint, targets
        )
        if verification_reason is not None:
            return self._result(
                False, "partial", None,
                {"attempted": True, "ok": False}, verification_reason,
                applied=applied,
            )
        if (
            not preserve_ownership
            and not self._replace_ownership(None, None)
        ):
            return self._result(
                False, "partial", None,
                {"attempted": True, "ok": True},
                "ownership_clear_failed",
                applied=applied,
            )
        return self._result(
            True, "restored", None, {"attempted": True, "ok": True},
            applied=applied,
        )

    def diagnostics(self):
        refresh_reason = self._refresh()
        policy_state = []
        for policy in self._policies:
            window = policy.read_window()
            policy_state.append({
                "name": policy.name,
                "cpus": list(policy.related_cpus),
                "related_cpus": list(policy.related_cpus),
                "affected_cpus": list(policy.affected_cpus),
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
            "durable_state_reason": self._durable_state_reason,
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
        related_text = read_str(os.path.join(path, "related_cpus"))
        affected_text = read_str(os.path.join(path, "affected_cpus"))
        if related_text is None:
            related_text = affected_text
        if affected_text is None:
            affected_text = related_text
        policies.append(Policy(
            name=os.path.basename(path),
            path=path,
            driver=read_str(os.path.join(path, "scaling_driver")),
            related_cpus=_parse_cpu_list(related_text),
            affected_cpus=_parse_cpu_list(affected_text),
            hardware_min_khz=values["hardware_min"],
            hardware_max_khz=values["hardware_max"],
        ))
    if not policies:
        return None, "no_policies"
    return policies, None


def select_cpu_frequency(
    root="/", persisted_state=None, persist_state=None, boot_id=None
):
    policies, reason = _discover_policies(root)
    if policies is None:
        return NullCpuFrequency(reason)
    return LinuxCpuFrequency(
        root,
        policies,
        persisted_state=persisted_state,
        persist_state=persist_state,
        boot_id=boot_id,
    )
