"""Intel RAPL powercap TDP backend (MSI Claw and other Intel handhelds whose
kernel exposes no firmware-attributes ppt_*). Synthetic powercap sysfs."""
import os

from tdp.intel_rapl import IntelRaplBackend
from tdp.runtime_lock import RuntimeSafetyLock
from tdp.types import TdpLimits

_FALLBACK = TdpLimits(min_w=8, default_w=17, max_w=30, max_ac_w=30)


def _mk_rapl(
    root,
    base,
    pl1_uw=30_000_000,
    pl2_uw=37_000_000,
    peak_uw=None,
    package_name="package-0",
):
    d = os.path.join(root, "sys/devices/virtual/powercap", base)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "name"), "w") as f:
        f.write(package_name)
    with open(os.path.join(d, "constraint_0_name"), "w") as f:
        f.write("long_term")
    with open(os.path.join(d, "constraint_0_power_limit_uw"), "w") as f:
        f.write(str(pl1_uw))
    with open(os.path.join(d, "constraint_1_name"), "w") as f:
        f.write("short_term")
    with open(os.path.join(d, "constraint_1_power_limit_uw"), "w") as f:
        f.write(str(pl2_uw))
    if peak_uw is not None:
        with open(os.path.join(d, "constraint_2_name"), "w") as f:
            f.write("peak_power")
        with open(os.path.join(d, "constraint_2_power_limit_uw"), "w") as f:
            f.write(str(peak_uw))
    return d


_MMIO = "intel-rapl-mmio/intel-rapl-mmio:0"
_LEGACY = "intel-rapl/intel-rapl:0"


def _read_uw(d, i):
    with open(os.path.join(d, f"constraint_{i}_power_limit_uw")) as f:
        return int(f.read().strip())


class TestIntelRapl:
    def test_unsupported_without_powercap(self, tmp_path):
        assert IntelRaplBackend(_FALLBACK, root=str(tmp_path)).supported is False

    def test_supported_with_mmio(self, tmp_path):
        _mk_rapl(str(tmp_path), _MMIO)
        assert IntelRaplBackend(_FALLBACK, root=str(tmp_path)).supported is True

    def test_auto_tdp_is_unsafe_while_pl2_remains_firmware_owned(self, tmp_path):
        _mk_rapl(str(tmp_path), _MMIO)
        backend = IntelRaplBackend(_FALLBACK, root=str(tmp_path))

        assert backend.auto_tdp_safe is False

    def test_auto_tdp_is_safe_with_named_pl1_pl2_on_every_surface(self, tmp_path):
        _mk_rapl(str(tmp_path), _MMIO, pl1_uw=22_000_000)
        _mk_rapl(str(tmp_path), _LEGACY)

        backend = IntelRaplBackend(_FALLBACK, root=str(tmp_path))

        assert backend.auto_tdp_safe is True

    def test_auto_tdp_rejects_a_non_package_rapl_surface(self, tmp_path):
        _mk_rapl(str(tmp_path), _MMIO)
        _mk_rapl(str(tmp_path), _LEGACY, package_name="core")

        backend = IntelRaplBackend(_FALLBACK, root=str(tmp_path))

        assert backend.auto_tdp_safe is False

    def test_auto_tdp_rejects_an_unreadable_limit(self, tmp_path):
        _mk_rapl(str(tmp_path), _MMIO)
        legacy = _mk_rapl(str(tmp_path), _LEGACY)
        with open(os.path.join(legacy, "constraint_1_power_limit_uw"), "w") as f:
            f.write("not-a-number")

        backend = IntelRaplBackend(_FALLBACK, root=str(tmp_path))

        assert backend.auto_tdp_safe is False

    def test_auto_tdp_writes_pl1_pl2_on_every_surface_and_ignores_peak(
        self, tmp_path
    ):
        mmio = _mk_rapl(
            str(tmp_path),
            _MMIO,
            pl1_uw=22_000_000,
            pl2_uw=37_000_000,
            peak_uw=95_000_000,
        )
        legacy = _mk_rapl(
            str(tmp_path),
            _LEGACY,
            pl1_uw=30_000_000,
            pl2_uw=37_000_000,
        )
        backend = IntelRaplBackend(_FALLBACK, root=str(tmp_path))

        result = backend.apply_auto_targets({"pl1": 18, "pl2": 18}, ac=True)

        assert result.ok is True
        assert _read_uw(mmio, 0) == 18_000_000
        assert _read_uw(mmio, 1) == 18_000_000
        assert _read_uw(mmio, 2) == 95_000_000
        assert _read_uw(legacy, 0) == 18_000_000
        assert _read_uw(legacy, 1) == 18_000_000

    def test_auto_tdp_orders_rails_safely_when_lowering_and_raising(
        self, tmp_path, monkeypatch
    ):
        _mk_rapl(str(tmp_path), _MMIO, pl1_uw=22_000_000, pl2_uw=37_000_000)
        _mk_rapl(str(tmp_path), _LEGACY, pl1_uw=30_000_000, pl2_uw=37_000_000)
        backend = IntelRaplBackend(_FALLBACK, root=str(tmp_path))
        real_write = backend._write
        rails = []

        def record_rail(path, value):
            rails.append("pl1" if "constraint_0_" in path else "pl2")
            return real_write(path, value)

        monkeypatch.setattr(backend, "_write", record_rail)

        assert backend.apply_auto_targets({"pl1": 18, "pl2": 18}, ac=True).ok
        assert rails == ["pl1", "pl1", "pl2", "pl2"]

        rails.clear()
        assert backend.apply_auto_targets({"pl1": 25, "pl2": 25}, ac=True).ok
        assert rails == ["pl2", "pl2", "pl1", "pl1"]

    def test_auto_tdp_partial_write_rolls_back_every_surface(
        self, tmp_path, monkeypatch
    ):
        mmio = _mk_rapl(
            str(tmp_path),
            _MMIO,
            pl1_uw=22_000_000,
            pl2_uw=37_000_000,
            peak_uw=95_000_000,
        )
        legacy = _mk_rapl(
            str(tmp_path),
            _LEGACY,
            pl1_uw=30_000_000,
            pl2_uw=37_000_000,
        )
        transaction_lock = tmp_path / "run/pdc/intel-rapl-transaction.lock"
        ownership_lock = tmp_path / "run/pdc/intel-rapl-ownership.lock"
        backend = IntelRaplBackend(
            _FALLBACK,
            root=str(tmp_path),
            safety_lock_path=str(transaction_lock),
            ownership_lock_path=str(ownership_lock),
        )
        real_write = backend._write
        failed_once = False

        def fail_legacy_pl2_once(path, value):
            nonlocal failed_once
            if path == os.path.join(legacy, "constraint_1_power_limit_uw") and not failed_once:
                failed_once = True
                return False
            return real_write(path, value)

        monkeypatch.setattr(backend, "_write", fail_legacy_pl2_once)

        result = backend.apply_auto_targets({"pl1": 18, "pl2": 18}, ac=True)

        assert result.ok is False
        assert _read_uw(mmio, 0) == 22_000_000
        assert _read_uw(mmio, 1) == 37_000_000
        assert _read_uw(mmio, 2) == 95_000_000
        assert _read_uw(legacy, 0) == 30_000_000
        assert _read_uw(legacy, 1) == 37_000_000
        assert not transaction_lock.exists()
        assert not ownership_lock.exists()

    def test_auto_tdp_rejects_unsafe_baseline_before_writing(
        self, tmp_path, monkeypatch
    ):
        _mk_rapl(str(tmp_path), _MMIO, pl1_uw=45_000_000)
        _mk_rapl(str(tmp_path), _LEGACY)
        backend = IntelRaplBackend(_FALLBACK, root=str(tmp_path))
        writes = []
        monkeypatch.setattr(
            backend,
            "_write",
            lambda path, value: writes.append((path, value)) or True,
        )

        result = backend.apply_auto_targets({"pl1": 18, "pl2": 18}, ac=True)

        assert result.ok is False
        assert result.detail == "RAPL snapshot outside the safe restore envelope"
        assert writes == []

    def test_auto_tdp_release_restores_original_limits(self, tmp_path):
        mmio = _mk_rapl(
            str(tmp_path),
            _MMIO,
            pl1_uw=22_000_000,
            pl2_uw=37_000_000,
        )
        legacy = _mk_rapl(
            str(tmp_path),
            _LEGACY,
            pl1_uw=30_000_000,
            pl2_uw=37_000_000,
        )
        ownership_lock = tmp_path / "run/pdc/intel-rapl-ownership.lock"
        backend = IntelRaplBackend(
            _FALLBACK,
            root=str(tmp_path),
            ownership_lock_path=str(ownership_lock),
        )

        assert backend.reselection_safe_after_use is False
        assert backend.apply_auto_targets({"pl1": 18, "pl2": 18}, ac=True).ok
        assert backend.reselection_safe_after_use is True
        assert ownership_lock.exists()
        assert backend.release() is True

        assert _read_uw(mmio, 0) == 22_000_000
        assert _read_uw(mmio, 1) == 37_000_000
        assert _read_uw(legacy, 0) == 30_000_000
        assert _read_uw(legacy, 1) == 37_000_000
        assert not ownership_lock.exists()
        assert backend.reselection_safe_after_use is False

    def test_auto_tdp_ownership_recovers_after_restart(self, tmp_path):
        mmio = _mk_rapl(
            str(tmp_path),
            _MMIO,
            pl1_uw=22_000_000,
            pl2_uw=37_000_000,
        )
        legacy = _mk_rapl(
            str(tmp_path),
            _LEGACY,
            pl1_uw=30_000_000,
            pl2_uw=37_000_000,
        )
        transaction_lock = tmp_path / "run/pdc/intel-rapl-transaction.lock"
        ownership_lock = tmp_path / "run/pdc/intel-rapl-ownership.lock"
        first = IntelRaplBackend(
            _FALLBACK,
            root=str(tmp_path),
            safety_lock_path=str(transaction_lock),
            ownership_lock_path=str(ownership_lock),
        )
        assert first.apply_auto_targets({"pl1": 18, "pl2": 18}, ac=True).ok

        restarted = IntelRaplBackend(
            _FALLBACK,
            root=str(tmp_path),
            safety_lock_path=str(transaction_lock),
            ownership_lock_path=str(ownership_lock),
        )

        assert restarted.safety_locked is True
        assert restarted.recover_runtime_transaction()["ok"] is True
        assert _read_uw(mmio, 0) == 22_000_000
        assert _read_uw(mmio, 1) == 37_000_000
        assert _read_uw(legacy, 0) == 30_000_000
        assert _read_uw(legacy, 1) == 37_000_000
        assert restarted.safety_locked is False

    def test_manual_write_after_auto_restores_pl2_and_legacy_surface(self, tmp_path):
        limits = TdpLimits(min_w=8, default_w=17, max_w=30, max_ac_w=35)
        mmio = _mk_rapl(
            str(tmp_path),
            _MMIO,
            pl1_uw=22_000_000,
            pl2_uw=37_000_000,
        )
        legacy = _mk_rapl(
            str(tmp_path),
            _LEGACY,
            pl1_uw=30_000_000,
            pl2_uw=37_000_000,
        )
        backend = IntelRaplBackend(limits, root=str(tmp_path))
        assert backend.auto_level_limits()["pl1"]["max"] == 30
        auto_result = backend.apply_auto_targets({"pl1": 35, "pl2": 35}, ac=True)
        assert auto_result.ok
        assert auto_result.applied_w == 30

        result = backend.set_tdp(35, ac=True)

        assert result.ok is True
        assert _read_uw(mmio, 0) == 35_000_000
        assert _read_uw(mmio, 1) == 37_000_000
        assert _read_uw(legacy, 0) == 30_000_000
        assert _read_uw(legacy, 1) == 37_000_000

    def test_auto_tdp_observes_both_surfaces_for_periodic_drift(self, tmp_path):
        _mk_rapl(str(tmp_path), _MMIO)
        legacy = _mk_rapl(str(tmp_path), _LEGACY)
        backend = IntelRaplBackend(_FALLBACK, root=str(tmp_path))
        assert backend.apply_auto_targets({"pl1": 18, "pl2": 18}, ac=True).ok
        assert backend.auto_observation_confirmed(
            backend.observe(),
            18,
            backend.read_tolerance_w,
        ) is True
        with open(os.path.join(legacy, "constraint_0_power_limit_uw"), "w") as f:
            f.write("25000000")

        values = backend.observe().applied_values()

        assert values == {
            ("intel-rapl", "pl1"): 18,
            ("intel-rapl", "pl2"): 18,
            ("intel-rapl:msr", "pl1"): 25,
            ("intel-rapl:msr", "pl2"): 18,
        }
        assert backend.auto_observation_confirmed(
            backend.observe(),
            18,
            backend.read_tolerance_w,
        ) is False

    def test_failed_rollback_blocks_until_transaction_and_ownership_recover(
        self, tmp_path, monkeypatch
    ):
        mmio = _mk_rapl(
            str(tmp_path),
            _MMIO,
            pl1_uw=22_000_000,
            pl2_uw=37_000_000,
        )
        legacy = _mk_rapl(
            str(tmp_path),
            _LEGACY,
            pl1_uw=30_000_000,
            pl2_uw=37_000_000,
        )
        transaction_lock = tmp_path / "run/pdc/intel-rapl-transaction.lock"
        ownership_lock = tmp_path / "run/pdc/intel-rapl-ownership.lock"
        backend = IntelRaplBackend(
            _FALLBACK,
            root=str(tmp_path),
            safety_lock_path=str(transaction_lock),
            ownership_lock_path=str(ownership_lock),
        )
        real_write = backend._write
        writes = 0

        def fail_apply_and_rollback(path, value):
            nonlocal writes
            writes += 1
            if writes >= 4:
                return False
            return real_write(path, value)

        monkeypatch.setattr(backend, "_write", fail_apply_and_rollback)

        result = backend.apply_auto_targets({"pl1": 18, "pl2": 18}, ac=True)

        assert result.ok is False
        assert backend.safety_locked is True
        assert backend.ready() is False
        assert backend.probe() is False
        assert transaction_lock.exists()
        assert ownership_lock.exists()

        monkeypatch.setattr(backend, "_write", real_write)
        assert backend.recover_runtime_transaction()["ok"] is True
        assert _read_uw(mmio, 0) == 22_000_000
        assert _read_uw(mmio, 1) == 37_000_000
        assert _read_uw(legacy, 0) == 30_000_000
        assert _read_uw(legacy, 1) == 37_000_000
        assert not transaction_lock.exists()
        assert not ownership_lock.exists()
        assert backend.safety_locked is False
        assert backend.ready() is True
        assert backend.probe() is True

    def test_recovery_rejects_out_of_range_snapshot_without_writing(
        self, tmp_path, monkeypatch
    ):
        _mk_rapl(str(tmp_path), _MMIO)
        _mk_rapl(str(tmp_path), _LEGACY)
        ownership_lock = tmp_path / "run/pdc/intel-rapl-ownership.lock"
        RuntimeSafetyLock(str(ownership_lock)).persist_payload(
            {
                "state": "ownership_pending",
                "detail": "test",
                "snapshot": {
                    "mmio/pl1": 22_000_000,
                    "mmio/pl2": 37_000_000,
                    "msr/pl1": 30_000_000,
                    "msr/pl2": 95_000_000,
                },
            }
        )
        backend = IntelRaplBackend(
            _FALLBACK,
            root=str(tmp_path),
            ownership_lock_path=str(ownership_lock),
        )
        writes = []
        monkeypatch.setattr(
            backend,
            "_write",
            lambda path, value: writes.append((path, value)) or True,
        )

        recovered = backend.recover_runtime_transaction()

        assert recovered["ok"] is False
        assert recovered["detail"] == "RAPL ownership snapshot invalid"
        assert writes == []
        assert ownership_lock.exists()
        assert backend.safety_locked is True

    def test_prefers_mmio_over_legacy(self, tmp_path):
        _mk_rapl(str(tmp_path), _LEGACY)
        d_mmio = _mk_rapl(str(tmp_path), _MMIO)
        b = IntelRaplBackend(_FALLBACK, root=str(tmp_path))
        b.set_tdp(20, True)
        assert _read_uw(d_mmio, 0) == 20_000_000  # wrote to mmio, not legacy

    def test_set_tdp_writes_pl1_in_microwatts_and_reads_back(self, tmp_path):
        d = _mk_rapl(str(tmp_path), _MMIO)
        b = IntelRaplBackend(_FALLBACK, root=str(tmp_path))
        res = b.set_tdp(20, True)
        assert _read_uw(d, 0) == 20_000_000
        assert res.applied_w == 20
        assert res.ok is True

    def test_set_tdp_only_owns_pl1_and_never_writes_observed_pl2(
        self, tmp_path, monkeypatch
    ):
        directory = _mk_rapl(
            str(tmp_path),
            _MMIO,
            pl1_uw=17_000_000,
            pl2_uw=31_000_000,
        )
        backend = IntelRaplBackend(_FALLBACK, root=str(tmp_path))
        real_write = backend._write
        writes = []

        def recording_write(path, value):
            writes.append((os.path.basename(path), value))
            return real_write(path, value)

        monkeypatch.setattr(backend, "_write", recording_write)

        result = backend.set_tdp(20, True)

        assert result.ok is True
        assert _read_uw(directory, 0) == 20_000_000
        assert _read_uw(directory, 1) == 31_000_000
        assert writes == [
            ("constraint_0_power_limit_uw", 20_000_000),
        ]

    def test_set_tdp_clamps_to_fallback_max(self, tmp_path):
        d = _mk_rapl(str(tmp_path), _MMIO)
        b = IntelRaplBackend(_FALLBACK, root=str(tmp_path))
        res = b.set_tdp(999, True)
        assert _read_uw(d, 0) == 30_000_000  # clamped to max_ac_w=30
        assert res.applied_w == 30

    def test_read_applied_converts_uw_to_w(self, tmp_path):
        _mk_rapl(str(tmp_path), _MMIO, pl1_uw=25_000_000)
        assert IntelRaplBackend(_FALLBACK, root=str(tmp_path)).read_applied() == 25

    def test_unsupported_set_tdp_never_raises(self, tmp_path):
        res = IntelRaplBackend(_FALLBACK, root=str(tmp_path)).set_tdp(20, True)
        assert res.ok is False

    def test_observe_reports_available_power_constraints(self, tmp_path):
        _mk_rapl(
            str(tmp_path),
            _MMIO,
            pl1_uw=25_000_000,
            pl2_uw=31_000_000,
        )
        b = IntelRaplBackend(_FALLBACK, root=str(tmp_path))
        rails = b.observe().surfaces["intel-rapl"]
        assert rails["pl1"].applied_w == 25
        assert rails["pl2"].applied_w == 31
        assert b.guard_interval_s == 2.0
        assert b.read_tolerance_w == 1
