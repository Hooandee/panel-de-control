import json
from pathlib import Path

import pytest

from device_profiles import DEVICE_TABLE
from tdp.msi_claw_a8 import MsiClawA8FirmwareBackend
from tdp.types import TdpLimits
from test_tdp_control_rpc import Plugin as Plugin


REPORT = json.loads(
    (Path(__file__).parent / 'fixtures/msi_claw_a8_ownership.json').read_text()
)
ATTRS = ('ppt_pl1_spl', 'ppt_pl2_sppt', 'ppt_pl3_fppt')


@pytest.fixture
def reported_a8(tmp_path, monkeypatch):
    def put(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(value))

    put(tmp_path / 'sys/class/dmi/id/board_name', REPORT['board_name'])
    paths = []
    for attr, lo, hi, value in zip(
        ATTRS, REPORT['rail_min'], REPORT['rail_max'], REPORT['current_levels'],
    ):
        folder = tmp_path / 'sys/class/firmware-attributes/msi-wmi-platform/attributes' / attr
        for leaf, item in [('min_value', lo), ('max_value', hi), ('current_value', value)]:
            put(folder / leaf, item)
        paths.append(folder / 'current_value')
    put(tmp_path / 'sys/firmware/acpi/platform_profile', REPORT['platform_profile'])
    put(tmp_path / 'sys/firmware/acpi/platform_profile_choices', REPORT['platform_profile_choices'])
    ownership = tmp_path / 'ownership.lock'
    ownership.write_text(json.dumps(REPORT['ownership']))
    transaction = tmp_path / 'transaction.lock'
    writes = []

    def create():
        backend = MsiClawA8FirmwareBackend(
            TdpLimits(6, 17, 35, 35), root=str(tmp_path),
            ownership_lock_path=str(ownership), safety_lock_path=str(transaction),
        )
        real_write = backend._write

        def write(path, value):
            writes.append((Path(path), value))
            if Path(path) in paths:
                folder = Path(path).parent
                if not int((folder / 'min_value').read_text()) <= value <= int((folder / 'max_value').read_text()):
                    backend._last_write_error = 'EINVAL'
                    return False
            return real_write(path, value)

        monkeypatch.setattr(backend, '_write', write)
        return backend

    return create, paths, ownership, transaction, writes


def _plugin(Plugin, backend):
    plugin = Plugin()
    plugin._init()
    plugin._device = next(p for p in DEVICE_TABLE if p.key == 'msi_claw_a8')
    plugin._os_id = 'bazzite'
    plugin._tdp_backend = backend
    plugin._tdp_external_owner = False
    plugin._settings['tdp_control_enabled'] = True
    return plugin


def test_report_restart_resumes_control_without_restoring_or_replacing_baseline(Plugin, reported_a8):
    create, paths, ownership, _transaction, writes = reported_a8
    original = ownership.read_bytes()
    backend = create()
    plugin = _plugin(Plugin, backend)

    assert plugin._recover_tdp_runtime_transaction() is True
    assert plugin._tdp_supported() is True
    assert writes == []
    assert ownership.read_bytes() == original
    assert backend.set_levels(18, 21, 25, ac=True).ok
    assert [int(p.read_text()) for p in paths] == [18, 21, 25]
    assert ownership.read_bytes() == original
    detail = backend.diagnostics()
    assert detail['owns_state'] is True
    assert detail['ownership_restore_pending'] is True
    assert detail['ownership_lock']['snapshot'] == {'pl1': 0, 'pl2': 0, 'pl3': 0}

    assert backend.release() is False
    assert ownership.read_bytes() == original
    assert backend.safety_locked is True
    assert all(value != 0 for _path, value in writes)
    assert backend.diagnostics()['owns_state'] is False

    restarted = create()
    plugin._tdp_backend = restarted
    assert plugin._recover_tdp_runtime_transaction() is True
    assert ownership.read_bytes() == original


@pytest.mark.parametrize('denial', ['disabled', 'steam', 'download', 'external', 'unknown_owner'])
def test_report_restart_never_resumes_without_authorization(Plugin, reported_a8, denial):
    create, _paths, ownership, _transaction, writes = reported_a8
    original = ownership.read_bytes()
    backend = create()
    plugin = _plugin(Plugin, backend)
    if denial == 'disabled':
        plugin._settings['tdp_control_enabled'] = False
    elif denial == 'steam':
        plugin._game_power_context_transition = True
    elif denial == 'download':
        from types import SimpleNamespace
        plugin._steam_download_hold = SimpleNamespace(holding=True)
    else:
        plugin._tdp_external_owner = True if denial == 'external' else None

    assert plugin._recover_tdp_runtime_transaction() is False
    assert plugin._tdp_supported() is False
    assert ownership.read_bytes() == original
    assert writes == []
    assert backend.relinquish_ownership()['ok'] is False
    assert ownership.exists()


@pytest.mark.parametrize('invalid', [0, 36, ''])
def test_report_restart_requires_all_current_rails_valid(Plugin, reported_a8, invalid):
    create, paths, ownership, _transaction, writes = reported_a8
    paths[0].write_text(str(invalid))
    plugin = _plugin(Plugin, create())
    assert plugin._recover_tdp_runtime_transaction() is False
    assert ownership.exists()
    assert writes == []


def test_report_interrupted_zero_transaction_is_not_resumed(Plugin, reported_a8):
    create, _paths, ownership, transaction, writes = reported_a8
    payload = {**REPORT['ownership'], 'state': 'transaction_pending'}
    transaction.write_text(json.dumps(payload))
    original = ownership.read_bytes()
    plugin = _plugin(Plugin, create())
    assert plugin._recover_tdp_runtime_transaction() is False
    assert transaction.exists()
    assert ownership.read_bytes() == original
    assert writes == []


def test_resumed_write_failure_rolls_back_current_values_preserving_original(Plugin, reported_a8, monkeypatch):
    create, paths, ownership, transaction, writes = reported_a8
    backend = create()
    plugin = _plugin(Plugin, backend)
    assert plugin._recover_tdp_runtime_transaction() is True
    original = ownership.read_bytes()
    write = backend._write

    def reject_pl2(path, value):
        if Path(path) == paths[1] and value == 21:
            backend._last_write_error = 'EINVAL'
            return False
        return write(path, value)

    monkeypatch.setattr(backend, '_write', reject_pl2)
    result = backend.set_levels(18, 21, 25, ac=True)
    assert result.ok is False
    assert 'rollback confirmed' in result.detail
    assert [int(p.read_text()) for p in paths] == [17, 20, 24]
    assert ownership.read_bytes() == original
    assert not transaction.exists()
    assert all(value != 0 for _path, value in writes)


def test_valid_original_ownership_still_restores_normally(Plugin, reported_a8):
    create, paths, ownership, _transaction, _writes = reported_a8
    payload = {**REPORT['ownership'], 'snapshot': {
        'msi-claw-a8-firmware/pl1': 15,
        'msi-claw-a8-firmware/pl2': 18,
        'msi-claw-a8-firmware/pl3': 22,
    }}
    ownership.write_text(json.dumps(payload))
    plugin = _plugin(Plugin, create())
    assert plugin._recover_tdp_runtime_transaction() is True
    assert [int(p.read_text()) for p in paths] == [15, 18, 22]
    assert not ownership.exists()


@pytest.mark.parametrize('owner', ['hhd', 'hhd_unknown', 'powerstation', 'powerstation_error'])
def test_report_external_manager_prevents_resume(Plugin, reported_a8, owner):
    from types import SimpleNamespace

    create, _paths, ownership, _transaction, writes = reported_a8
    original = ownership.read_bytes()
    plugin = _plugin(Plugin, create())
    if owner.startswith('hhd'):
        plugin._controller_backend = SimpleNamespace(manager='hhd')
        plugin._hhd_tdp_client = SimpleNamespace(
            current_tdp_enable=lambda: True if owner == 'hhd' else None,
        )
    else:
        def active():
            if owner == 'powerstation_error':
                raise OSError('unavailable')
            return True
        plugin._powerstation_detector = SimpleNamespace(tdp_active=active)
    assert plugin._recover_tdp_runtime_transaction() is False
    assert plugin._tdp_supported() is False
    assert ownership.read_bytes() == original
    assert writes == []


def test_crashed_resumed_write_restores_transaction_before_resuming(Plugin, reported_a8):
    create, paths, ownership, transaction, _writes = reported_a8
    original = ownership.read_bytes()
    transaction.write_text(json.dumps({
        'state': 'transaction_pending',
        'snapshot': {
            'msi-claw-a8-firmware/pl1': 17,
            'msi-claw-a8-firmware/pl2': 20,
            'msi-claw-a8-firmware/pl3': 24,
        },
        'profile': None,
    }))
    paths[2].write_text('25')
    backend = create()
    plugin = _plugin(Plugin, backend)
    assert plugin._recover_tdp_runtime_transaction() is False
    assert [int(p.read_text()) for p in paths] == [17, 20, 24]
    assert not transaction.exists()
    assert ownership.read_bytes() == original
    assert backend.diagnostics()['owns_state'] is False
    assert plugin._recover_tdp_runtime_transaction() is True
    assert ownership.read_bytes() == original


def test_control_disabled_rpc_keeps_failed_handoff_and_does_not_resume(Plugin, reported_a8):
    import asyncio

    create, _paths, ownership, _transaction, writes = reported_a8
    original = ownership.read_bytes()
    backend = create()
    plugin = _plugin(Plugin, backend)
    assert plugin._recover_tdp_runtime_transaction() is True
    assert asyncio.run(plugin.set_tdp_control_enabled(False)) is False
    assert plugin._settings['tdp_control_enabled'] is False
    assert plugin._tdp_reason == 'release_failed'
    assert plugin._recover_tdp_runtime_transaction() is False
    assert ownership.read_bytes() == original
    assert writes == []


def test_cold_boot_snapshot_remains_original_after_release_and_resume(Plugin, reported_a8):
    create, paths, ownership, _transaction, writes = reported_a8
    ownership.unlink()
    for path in paths:
        path.write_text('0')
    backend = create()
    assert backend.set_levels(17, 20, 24, ac=True).ok
    payload = json.loads(ownership.read_text())
    assert payload['snapshot'] == REPORT['ownership']['snapshot']
    assert payload['profile'] is None
    original = ownership.read_bytes()
    writes.clear()
    assert backend.release() is False
    assert writes == []
    plugin = _plugin(Plugin, create())
    assert plugin._recover_tdp_runtime_transaction() is True
    assert ownership.read_bytes() == original


def test_resume_rejects_different_board_even_with_msi_marker(Plugin, reported_a8, tmp_path):
    create, _paths, ownership, _transaction, writes = reported_a8
    (tmp_path / 'sys/class/dmi/id/board_name').write_text('MS-1T42')
    backend = create()
    plugin = _plugin(Plugin, backend)
    assert plugin._recover_tdp_runtime_transaction() is False
    assert backend.diagnostics()['owns_state'] is False
    assert ownership.exists()
    assert all(value == 0 for _path, value in writes)


def test_explicit_enable_resumes_after_disabled_handoff_without_replacing_baseline(Plugin, reported_a8):
    import asyncio

    create, paths, ownership, _transaction, _writes = reported_a8
    original = ownership.read_bytes()
    backend = create()
    plugin = _plugin(Plugin, backend)
    assert plugin._recover_tdp_runtime_transaction() is True
    assert asyncio.run(plugin.set_tdp_control_enabled(False)) is False
    assert plugin._settings['tdp_control_enabled'] is False
    assert asyncio.run(plugin.set_tdp_control_enabled(True)) is True
    assert plugin._settings['tdp_control_enabled'] is True
    assert plugin._tdp_supported() is True
    assert backend.set_levels(18, 21, 25, ac=True).ok
    assert [int(p.read_text()) for p in paths] == [18, 21, 25]
    assert ownership.read_bytes() == original


@pytest.mark.parametrize('denial', ['external', 'game', 'download'])
def test_explicit_enable_does_not_override_other_owner(Plugin, reported_a8, denial):
    import asyncio
    from types import SimpleNamespace

    create, _paths, ownership, _transaction, writes = reported_a8
    original = ownership.read_bytes()
    plugin = _plugin(Plugin, create())
    plugin._settings['tdp_control_enabled'] = False
    if denial == 'external':
        plugin._tdp_external_owner = True
    elif denial == 'game':
        plugin._game_power_context_transition = True
    else:
        plugin._steam_download_hold = SimpleNamespace(holding=True)
    assert asyncio.run(plugin.set_tdp_control_enabled(True)) is False
    assert plugin._settings['tdp_control_enabled'] is False
    assert ownership.read_bytes() == original
    assert writes == []


def test_cancelled_enable_does_not_resume_after_owner_probe_returns(Plugin, reported_a8):
    import asyncio
    import threading
    from types import SimpleNamespace

    create, _paths, ownership, _transaction, writes = reported_a8
    original = ownership.read_bytes()
    backend = create()
    plugin = _plugin(Plugin, backend)
    plugin._settings['tdp_control_enabled'] = False
    started = threading.Event()
    finish = threading.Event()

    def current_owner():
        started.set()
        assert finish.wait(5)
        return False

    plugin._controller_backend = SimpleNamespace(manager='hhd')
    plugin._hhd_tdp_client = SimpleNamespace(current_tdp_enable=current_owner)

    async def cancel_during_probe():
        task = asyncio.create_task(plugin.set_tdp_control_enabled(True))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            finish.set()
        await plugin._offload_call(lambda: None)

    asyncio.run(cancel_during_probe())
    assert plugin._settings['tdp_control_enabled'] is False
    assert backend.safety_locked is True
    assert backend.diagnostics()['owns_state'] is False
    assert ownership.read_bytes() == original
    assert writes == []


def test_owner_change_during_probe_prevents_resume(Plugin, reported_a8):
    from types import SimpleNamespace

    create, _paths, ownership, _transaction, writes = reported_a8
    backend = create()
    plugin = _plugin(Plugin, backend)

    def current_owner():
        plugin._game_power_context_transition = True
        plugin._advance_tdp_generation()
        return False

    plugin._controller_backend = SimpleNamespace(manager='hhd')
    plugin._hhd_tdp_client = SimpleNamespace(current_tdp_enable=current_owner)
    assert plugin._recover_tdp_runtime_transaction() is False
    assert backend.safety_locked is True
    assert ownership.exists()
    assert writes == []


def test_resumed_control_does_not_start_write_with_new_invalid_readback(Plugin, reported_a8):
    create, paths, ownership, transaction, writes = reported_a8
    original = ownership.read_bytes()
    backend = create()
    plugin = _plugin(Plugin, backend)
    assert plugin._recover_tdp_runtime_transaction() is True
    paths[1].write_text('0')
    assert backend.set_levels(18, 21, 25, ac=True).ok is False
    assert writes == []
    assert not transaction.exists()
    assert ownership.read_bytes() == original
