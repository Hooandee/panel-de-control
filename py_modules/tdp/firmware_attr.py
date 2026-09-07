import glob
import os
import time

from sysfs import read_str
from tdp.backend import TDPBackend
from tdp.runtime_lock import RuntimeSafetyLock
from tdp.types import RailReading, TdpLimits, TdpObservation, TdpResult

_FW_BASE = "sys/class/firmware-attributes"
_PP_BASE = "sys/class/platform-profile"
# ASUS exposes a SECOND, legacy PL1 interface (asus-nb-wmi: direct ppt files) that Steam
# and HHD also write. The effective SoC limit is the last write across BOTH interfaces,
# so a write mirrors our (clamped) setpoint here too to stay authoritative under a game.
_LEGACY_BASE = "sys/devices/platform/asus-nb-wmi"
_LEGACY_NODES = (("pl1", "ppt_pl1_spl"), ("pl2", "ppt_pl2_sppt"), ("pl3", "ppt_fppt"))
_RAIL_ATTRS = (
    ("pl1", "ppt_pl1_spl"),
    ("pl2", "ppt_pl2_sppt"),
    ("pl3", "ppt_pl3_fppt"),
)

# Boost headroom derived from sustained PL1 when the user sets a single TDP value.
# PL2 (slow) and PL3 (fast) are scaled above PL1, then clamped to each rail's sysfs max.
_PL2_BOOST_RATIO = 1.2
_PL3_BOOST_RATIO = 1.4


def _normalise_rail_floors(values):
    if not isinstance(values, dict):
        return {}
    known_rails = {rail for rail, _attr in _RAIL_ATTRS}
    floors = {}
    for rail, value in values.items():
        if rail not in known_rails:
            continue
        try:
            floor = int(value)
        except (TypeError, ValueError):
            continue
        if floor > 0:
            floors[rail] = floor
    return floors


def _normalise_rail_values(values):
    if not isinstance(values, dict):
        return {}
    known_rails = {rail for rail, _attr in _RAIL_ATTRS}
    normalised = {}
    for rail, value in values.items():
        if rail not in known_rails:
            continue
        try:
            normalised[rail] = int(value)
        except (TypeError, ValueError):
            continue
    return normalised


class FirmwareAttrBackend(TDPBackend):
    """TDP via kernel firmware-attributes. Covers ASUS (asus-armoury), Lenovo
    (lenovo-wmi-other), MSI (msi-wmi-platform): ppt_pl1_spl/ppt_pl2_sppt/ppt_pl3_fppt
    with current_value (watts) + min_value/max_value. Never raises."""

    def __init__(
        self,
        driver_prefix,
        fallback,
        root="/",
        profile_name=None,
        is_generic=False,
        rail_floors=None,
        ignored_live_maxes=None,
        cap_boost_to_active=False,
        readback_settle_delays=None,
        authoritative_reassert_s=None,
        trust_live_bounds=False,
        safety_lock_path=None,
    ):
        self.name = f"firmware-attr:{driver_prefix}"
        self._fallback = fallback
        self._root = root
        self._profile_name = profile_name  # Lenovo: set this platform-profile to "custom" first
        self._is_generic = is_generic
        self._trust_live_bounds = bool(trust_live_bounds)
        self._safety_lock = RuntimeSafetyLock(safety_lock_path)
        self._rail_floors = _normalise_rail_floors(rail_floors)
        self._ignored_live_maxes = _normalise_rail_values(ignored_live_maxes)
        self.cap_boost_to_active = bool(cap_boost_to_active)
        self._readback_settle_delays = tuple(
            float(delay) for delay in (readback_settle_delays or ())
        )
        self._dir = self._find_driver_dir(driver_prefix)
        self.supported = self._dir is not None and os.path.exists(self._attr("ppt_pl1_spl"))
        self._pp_dir = self._find_profile_dir()  # static, resolved once
        self._pp_choices = None                  # parsed lazily, then cached
        self._legacy = self._find_legacy_nodes(driver_prefix)  # ASUS dual-interface
        self._primary_rails = tuple(
            rail
            for rail, attr in _RAIL_ATTRS
            if os.path.exists(self._attr(attr))
        )
        self._rails = tuple(
            rail
            for rail, _attr in _RAIL_ATTRS
            if rail in self._primary_rails or rail in self._legacy
        )
        self.supports_levels = any(rail != "pl1" for rail in self._rails)
        self._runtime_lock_payload = self._safety_lock.load_payload()
        self._write_circuit_open = (
            self._runtime_lock_payload.get("detail")
            or self._runtime_lock_payload.get("state")
            if self._runtime_lock_payload
            else None
        )
        complete_primary = all(rail in self._primary_rails for rail, _attr in _RAIL_ATTRS)
        complete_legacy = all(rail in self._legacy for rail, _attr in _RAIL_ATTRS)
        try:
            reassert_s = float(authoritative_reassert_s)
        except (TypeError, ValueError):
            reassert_s = 0.0
        self.authoritative_reassert_s = (
            reassert_s
            if driver_prefix == "asus-armoury"
            and complete_primary
            and complete_legacy
            and reassert_s > 0
            else None
        )

    def _live_bounds(self, attr):
        # Read live, never cache: the firmware ceiling is dynamic.
        lo = self._read_int(self._attr(attr, "min_value"))
        hi = self._read_int(self._attr(attr, "max_value"))
        return lo, hi

    @staticmethod
    def _rail_for_attr(attr):
        return next(
            (rail for rail, rail_attr in _RAIL_ATTRS if rail_attr == attr),
            None,
        )

    def _static_bounds(self, attr):
        rail = self._rail_for_attr(attr)
        hi = self._profile_rail_max(attr)
        lo = max(
            self._fallback.min_w,
            self._rail_floors.get(rail, self._fallback.min_w),
        )
        return min(lo, hi), hi

    def _validated_live_bounds(self, attr):
        mn, reported_max = self._live_bounds(attr)
        rail = self._rail_for_attr(attr)
        mx = self._effective_live_max(rail, reported_max)
        if (
            mn is None
            or mx is None
            or mn <= 0
            or mx <= 0
            or mn > mx
        ):
            return None
        static_lo, static_hi = self._static_bounds(attr)
        lo = max(static_lo, mn)
        hi = min(static_hi, mx)
        return (lo, hi) if lo <= hi else None

    def _find_legacy_nodes(self, driver_prefix):
        """Detect the legacy asus-nb-wmi ppt files (the second PL1 interface). ASUS only;
        empty on other vendors and on kernels that dropped the legacy nodes."""
        if not driver_prefix.startswith("asus"):
            return {}
        base = os.path.join(self._root, _LEGACY_BASE)
        return {rail: os.path.join(base, node)
                for rail, node in _LEGACY_NODES
                if os.path.exists(os.path.join(base, node))}

    def _transaction_surfaces(self, targets):
        attrs = dict(_RAIL_ATTRS)
        primary = [
            (self.name, rail, self._attr(attrs[rail]))
            for rail in reversed(self._rails)
            if rail in self._primary_rails and rail in targets
        ]
        legacy = [
            ("asus-nb-wmi", rail, self._legacy[rail])
            for rail in ("pl3", "pl2", "pl1")
            if rail in self._legacy and rail in targets
        ]
        return primary + legacy

    @staticmethod
    def _surface_label(surface, rail):
        return f"{surface}/{rail}"

    def _capture_transaction(self, surfaces):
        snapshot = {}
        missing = []
        for surface, rail, path in surfaces:
            value = self._read_int(path)
            if value is None:
                missing.append(f"{self._surface_label(surface, rail)}=unavailable")
            else:
                snapshot[path] = value
        profile = self.read_profile() if self._pp_dir else None
        if self._pp_dir and profile is None:
            missing.append("platform-profile=unavailable")
        return snapshot, profile, missing

    def _snapshot_mismatches(self, surfaces, snapshot, profile):
        mismatches = []
        for surface, rail, path in surfaces:
            current = self._read_int(path)
            expected = snapshot[path]
            if current is None:
                mismatches.append(f"{self._surface_label(surface, rail)}=unavailable")
            elif current != expected:
                mismatches.append(f"{self._surface_label(surface, rail)}={current}")
        if self._pp_dir:
            current_profile = self.read_profile()
            if current_profile is None:
                mismatches.append("platform-profile=unavailable")
            elif current_profile != profile:
                mismatches.append(f"platform-profile={current_profile}")
        return mismatches

    def _rollback_transaction(self, surfaces, snapshot, profile):
        write_failures = []
        for surface, rail, path in reversed(surfaces):
            if not self._write(path, snapshot[path]):
                write_failures.append(self._surface_label(surface, rail))
        if self._pp_dir and not self._write(
            os.path.join(self._pp_dir, "profile"),
            profile,
        ):
            write_failures.append("platform-profile")

        mismatches = self._snapshot_mismatches(surfaces, snapshot, profile)
        for delay in self._readback_settle_delays:
            if not mismatches:
                break
            time.sleep(delay)
            mismatches = self._snapshot_mismatches(surfaces, snapshot, profile)
        return not mismatches, write_failures + mismatches

    def recover_runtime_transaction(self):
        payload = self._runtime_lock_payload
        saved = payload.get("snapshot") if isinstance(payload, dict) else None
        if not isinstance(saved, dict) or not saved:
            return {"ok": False, "detail": "firmware recovery snapshot unavailable"}
        surfaces = self._transaction_surfaces({rail: 0 for rail in self._rails})
        current = {
            self._surface_label(surface, rail): path
            for surface, rail, path in surfaces
        }
        if set(saved) != set(current):
            return {"ok": False, "detail": "firmware recovery surfaces changed"}
        try:
            snapshot = {current[label]: int(value) for label, value in saved.items()}
        except (TypeError, ValueError):
            return {"ok": False, "detail": "firmware recovery snapshot invalid"}
        profile = payload.get("profile")
        if self._pp_dir and not isinstance(profile, str):
            return {"ok": False, "detail": "firmware recovery profile unavailable"}
        recovered, problems = self._rollback_transaction(surfaces, snapshot, profile)
        if not recovered:
            detail = "firmware recovery failed: " + ", ".join(problems)
            payload = {**payload, "state": "rollback_failed", "detail": detail}
            self._runtime_lock_payload = payload
            self._write_circuit_open = detail
            self._safety_lock.persist_payload(payload)
            return {"ok": False, "detail": detail}
        if not self._safety_lock.clear():
            detail = "firmware recovery confirmed; runtime lock clear failed"
            self._write_circuit_open = detail
            return {"ok": False, "detail": detail}
        self._runtime_lock_payload = None
        self._write_circuit_open = None
        return {"ok": True, "detail": "firmware transaction recovered"}

    def reconciliation_levels(self, levels):
        return {
            rail: int(levels[rail])
            for rail in self._rails
            if rail in levels
        }

    def _find_driver_dir(self, prefix):
        base = os.path.join(self._root, _FW_BASE)
        for d in sorted(glob.glob(os.path.join(base, prefix + "*"))):
            if os.path.isdir(os.path.join(d, "attributes")):
                return d
        return None

    def _attr(self, name, leaf="current_value"):
        return os.path.join(self._dir or "", "attributes", name, leaf)

    def _read_int(self, path):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def _write(self, path, value):
        try:
            with open(path, "w") as f:
                f.write(f"{value}\n")
            return True
        except OSError:
            return False

    def get_limits(self):
        if not self.supported:
            return self._fallback
        if not self._is_generic and not self._trust_live_bounds:
            # The profile is the authority for the range; the firmware's reported max
            # lies (and, cached, stranded users at 15 W). Writes still clamp live.
            return self._fallback
        if self._trust_live_bounds:
            live = self._validated_live_bounds("ppt_pl1_spl")
            if live is None:
                return self._fallback
            mn, mx = live
        else:
            mn, mx = self._live_bounds("ppt_pl1_spl")
        max_ac_w = min(
            self._fallback.max_ac_w,
            mx if mx is not None else self._fallback.max_ac_w,
        )
        max_w = min(self._fallback.max_w, max_ac_w)
        live_min = mn if mn is not None else self._fallback.min_w
        min_w = min(max_w, max(self._fallback.min_w, live_min))
        default_w = max(min_w, min(self._fallback.default_w, max_w))
        return TdpLimits(
            min_w=min_w,
            default_w=default_w,
            max_w=max_w,
            max_ac_w=max_ac_w,
        )

    def ready(self):
        if not self.supported or self._write_circuit_open is not None:
            return False
        if not self._trust_live_bounds:
            return True
        return all(
            self._validated_live_bounds(attr) is not None
            for rail, attr in _RAIL_ATTRS
            if rail in self._primary_rails
        )

    @property
    def safety_locked(self):
        return self._write_circuit_open is not None

    def probe(self):
        return self.ready()

    def _find_profile_dir(self):
        if not self._profile_name:
            return None
        base = os.path.join(self._root, _PP_BASE)
        for d in sorted(glob.glob(os.path.join(base, "*"))):
            if read_str(os.path.join(d, "name")) == self._profile_name:
                return d
        return None

    def read_profile(self):
        """Active firmware profile (e.g. 'performance', 'custom'), or None. Read live —
        the active profile changes when the user picks a mode."""
        return read_str(os.path.join(self._pp_dir, "profile")) if self._pp_dir else None

    def profile_choices(self):
        """Available firmware profiles, e.g. ['low-power','balanced','performance',
        'custom']. Static, cached. Empty when unsupported."""
        if self._pp_choices is None:
            raw = read_str(os.path.join(self._pp_dir, "choices")) if self._pp_dir else None
            self._pp_choices = raw.split() if raw else []
        return self._pp_choices

    def set_profile(self, mode):
        """Write a named firmware profile. Returns True on confirmed readback; False
        for an unknown mode or when unsupported."""
        if not self._pp_dir or mode not in self.profile_choices():
            return False
        self._write(os.path.join(self._pp_dir, "profile"), mode)
        return self.read_profile() == mode

    def level_limits(self):
        if self._trust_live_bounds:
            return {
                key: {"min": bounds[0], "max": bounds[1]}
                for key, attr in _RAIL_ATTRS
                if key in self._rails
                for bounds in (
                    self._validated_live_bounds(attr)
                    or self._static_bounds(attr),
                )
            }
        if self._is_generic:
            out = {}
            for key, attr in _RAIL_ATTRS:
                if key not in self._rails:
                    continue
                mn, mx = self._live_bounds(attr)
                if mn is not None and mx is not None:
                    hi = min(mx, self._profile_rail_max(attr))
                    lo = min(
                        hi,
                        max(
                            self._fallback.min_w,
                            mn,
                            self._rail_floors.get(key, self._fallback.min_w),
                        ),
                    )
                    out[key] = {"min": lo, "max": hi}
            return out
        mn = self._fallback.min_w
        bounds = {
            rail: {"min": mn, "max": self._profile_rail_max(attr)}
            for rail, attr in _RAIL_ATTRS
        }
        for rail, floor in self._rail_floors.items():
            bound = bounds[rail]
            bound["min"] = min(bound["max"], max(bound["min"], floor))
        return {rail: bounds[rail] for rail in self._rails}

    def _profile_rail_max(self, attr):
        """Recognised-device write ceiling for a rail, mirroring level_limits(): PL1 =
        charger max, boost rails profile-scaled. The profile is the authority — not the
        firmware's reported max, which some ASUS kernels report as a bogus 150 W."""
        mx = self._fallback.max_ac_w
        if self.cap_boost_to_active:
            return mx
        if attr == "ppt_pl2_sppt":
            return round(mx * _PL2_BOOST_RATIO)
        if attr == "ppt_pl3_fppt":
            return round(mx * _PL3_BOOST_RATIO)
        return mx

    def _effective_live_max(self, rail, reported):
        if reported == self._ignored_live_maxes.get(rail):
            return None
        return reported

    def _clamp_live(self, value, attr):
        mn, mx = self._live_bounds(attr)
        safe_hi = self._profile_rail_max(attr)
        rail = self._rail_for_attr(attr)
        live_hi = self._effective_live_max(rail, mx)
        hi = min(live_hi if live_hi is not None else safe_hi, safe_hi)
        live_lo = mn if mn is not None else self._fallback.min_w
        floor = self._rail_floors.get(rail, self._fallback.min_w)
        lo = min(hi, max(self._fallback.min_w, live_lo, floor))
        return max(lo, min(int(value), hi))

    def set_levels(self, pl1, pl2, pl3, ac):
        if not self.supported:
            return TdpResult(pl1, None, False, "firmware-attributes path not present")
        if self._write_circuit_open is not None:
            return TdpResult(
                pl1,
                self.read_applied(),
                False,
                f"firmware write circuit open: {self._write_circuit_open}",
            )
        if self._trust_live_bounds and any(
            self._validated_live_bounds(attr) is None
            for rail, attr in _RAIL_ATTRS
            if rail in self._primary_rails
        ):
            return TdpResult(pl1, self.read_applied(), False, "firmware live bounds invalid")
        values = {"pl1": pl1, "pl2": pl2, "pl3": pl3}
        attrs = dict(_RAIL_ATTRS)
        targets = {
            rail: self._clamp_live(values[rail], attrs[rail])
            for rail in self._rails
        }
        surfaces = self._transaction_surfaces(targets)
        snapshot, previous_profile, missing = self._capture_transaction(surfaces)
        if missing:
            return TdpResult(
                pl1,
                self.read_applied(),
                False,
                "transaction snapshot unavailable: "
                + ", ".join(missing)
                + "; no writes performed",
            )
        lock_payload = {
            "state": "transaction_pending",
            "detail": "firmware transaction pending",
            "snapshot": {
                self._surface_label(surface, rail): snapshot[path]
                for surface, rail, path in surfaces
            },
            "profile": previous_profile,
        }
        if not self._safety_lock.persist_payload(lock_payload):
            return TdpResult(
                pl1,
                self.read_applied(),
                False,
                "transaction safety lock unavailable; no writes performed",
            )
        self._runtime_lock_payload = lock_payload

        failed = []
        if self._pp_dir:
            profile_path = os.path.join(self._pp_dir, "profile")
            if not self._write(profile_path, "custom"):
                failed.append("platform-profile")
            else:
                current_profile = self.read_profile()
                if current_profile != "custom":
                    failed.append(
                        "platform-profile="
                        + (current_profile if current_profile is not None else "unavailable")
                    )
        if not failed:
            for surface, rail, path in surfaces:
                if not self._write(path, targets[rail]):
                    failed.append(self._surface_label(surface, rail))
                    break

        observation = self.observe()
        mismatches = self._observation_mismatches(observation, targets)
        if not failed:
            for delay in self._readback_settle_delays:
                if not mismatches:
                    break
                time.sleep(delay)
                observation = self.observe()
                mismatches = self._observation_mismatches(
                    observation,
                    targets,
                )
        applied = observation.surfaces.get(self.name, {}).get("pl1")
        applied_w = applied.applied_w if applied else None
        problems = failed + mismatches
        if problems:
            rollback_ok, rollback_problems = self._rollback_transaction(
                surfaces,
                snapshot,
                previous_profile,
            )
            rollback_detail = "rollback confirmed"
            if not rollback_ok:
                rollback_detail = "rollback failed: " + ", ".join(rollback_problems)
                self._write_circuit_open = rollback_detail
                lock_payload = {
                    **lock_payload,
                    "state": "rollback_failed",
                    "detail": rollback_detail,
                }
                self._runtime_lock_payload = lock_payload
                if not self._safety_lock.persist_payload(lock_payload):
                    self._write_circuit_open += "; runtime lock persistence failed"
            elif not self._safety_lock.clear():
                rollback_detail += "; runtime lock clear failed"
                self._write_circuit_open = rollback_detail
            else:
                self._runtime_lock_payload = None
            restored_applied_w = (
                self._read_int(self._attr("ppt_pl1_spl"))
                if applied_w is not None
                else None
            )
            return TdpResult(
                pl1,
                restored_applied_w,
                False,
                "write not confirmed: "
                + ", ".join(problems)
                + "; "
                + rollback_detail,
            )
        if not self._safety_lock.clear():
            self._write_circuit_open = "write confirmed; runtime lock clear failed"
            return TdpResult(
                pl1,
                applied_w,
                False,
                self._write_circuit_open,
            )
        self._runtime_lock_payload = None
        return TdpResult(
            pl1,
            applied_w,
            True,
            "",
        )

    def set_tdp(self, watts, ac):
        # Single-value entry: write all rails flat (SPPT = FPPT = PL1). Boost headroom
        # is opt-in via set_levels, never implied by a bare TDP value.
        if not self.supported:
            return TdpResult(watts, None, False, "firmware-attributes path not present")
        lim = self.get_limits()
        target = lim.clamp(watts, ac)
        return self.set_levels(target, target, target, ac)

    def read_applied(self):
        primary = self.observe().surfaces.get(self.name, {})
        reading = primary.get("pl1")
        return reading.applied_w if reading else None

    def observe(self):
        if not self.supported:
            return TdpObservation(readable=True)
        primary = {}
        for rail, attr in _RAIL_ATTRS:
            path = self._attr(attr)
            if not os.path.exists(path):
                continue
            lo, hi = self._live_bounds(attr)
            primary[rail] = RailReading(
                self._read_int(path),
                lo,
                self._effective_live_max(rail, hi),
            )
        surfaces = {self.name: primary} if primary else {}
        legacy = {
            rail: RailReading(self._read_int(path))
            for rail, path in self._legacy.items()
        }
        if legacy:
            surfaces["asus-nb-wmi"] = legacy
        return TdpObservation(readable=True, surfaces=surfaces)

    def diagnostics(self):
        reported = {}
        for rail, attr in _RAIL_ATTRS:
            if rail not in self._rails:
                continue
            lo, hi = self._live_bounds(attr)
            reported[rail] = {"min": lo, "max": hi}
        diagnostics = {
            "boost_capped_to_active": self.cap_boost_to_active,
            "ignored_live_maxes": dict(self._ignored_live_maxes),
            "readback_settle_ms": round(
                sum(self._readback_settle_delays) * 1000
            ),
            "reported_live_bounds": reported,
        }
        if self._write_circuit_open is not None:
            diagnostics["write_circuit_open"] = self._write_circuit_open
        if self._trust_live_bounds:
            diagnostics["live_bounds_valid"] = {
                rail: self._validated_live_bounds(attr) is not None
                for rail, attr in _RAIL_ATTRS
                if rail in self._rails
            }
        return diagnostics

    def _observation_mismatches(self, observation, targets):
        bad = []
        for surface, rails in (
            (self.name, self._primary_rails),
            ("asus-nb-wmi", self._legacy),
        ):
            observed = observation.surfaces.get(surface, {})
            for rail in rails:
                if rail not in targets:
                    continue
                reading = observed.get(rail)
                if reading is None or reading.applied_w is None:
                    bad.append(f"{surface}/{rail}=unavailable")
                elif reading.applied_w != targets[rail]:
                    bad.append(f"{surface}/{rail}={reading.applied_w}")
        return bad
