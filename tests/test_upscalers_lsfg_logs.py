import json
import os
import time
import tomllib
from pathlib import Path

import pytest

from test_upscalers_lsfg_update import payload
from upscalers import lsfg
from upscalers.lsfg_logs import RuntimeLog, RETAIN_BYTES, MAX_BYTES


def test_owned_profile_enables_private_log_and_report(tmp_path):
    home = tmp_path / 'home'
    engine = lsfg.Lsfg(str(home), tmp_path / 'state')
    try:
        engine.install(payload(tmp_path / 'bundle', b'layer'), '2.0.0')
        engine.set_game('292030', 'Witcher', {'multiplier': 2}, 'witcher3.exe')
        config = tomllib.loads(engine.config_path.read_text())
        path = Path(config['global']['log_file'])
        assert path == engine.runtime_log.path
        assert config['global']['log_level'] == 'info'
        assert path.stat().st_mode & 0o777 == 0o600
        path.write_text(f'profile=pdc-292030 multiplier=2 {home}/secret/game.exe token=private-token\n')
        report = engine.report()['runtime_log']
        assert report['available'] is True
        assert report['generation_confirmed'] is None
        assert 'pdc-292030' in json.dumps(report)
        assert str(home) not in json.dumps(report)
        assert 'private-token' not in json.dumps(report)
    finally:
        engine.close()


def test_retention_keeps_inode_and_open_append_writer(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    log = RuntimeLog(home)
    assert log.prepare()
    with log.path.open('ab', buffering=0) as writer:
        writer.write(b'old\n' * MAX_BYTES)
        writer.write(b'recent\n')
        inode = log.path.stat().st_ino
        log.maintain()
        assert log.path.stat().st_ino == inode
        assert log.path.stat().st_size <= RETAIN_BYTES
        writer.write(b'after trim\n')
    assert log.path.read_bytes().endswith(b'recent\nafter trim\n')


@pytest.mark.parametrize('kind', ['symlink', 'parent_symlink', 'fifo', 'hardlink'])
def test_refuses_unsafe_log_without_touching_target(tmp_path, kind):
    home = tmp_path / 'home'
    home.mkdir()
    log = RuntimeLog(home)
    log.path.parent.mkdir(parents=True)
    victim = tmp_path / 'private'
    victim.write_text('do not touch')
    if kind == 'symlink':
        log.path.symlink_to(victim)
    elif kind == 'parent_symlink':
        log.path.parent.rmdir()
        log.path.parent.symlink_to(tmp_path, target_is_directory=True)
    elif kind == 'fifo':
        os.mkfifo(log.path)
    else:
        os.link(victim, log.path)
    assert not log.prepare()
    log.maintain()
    assert log.report()['available'] is False
    assert victim.read_text() == 'do not touch'


def test_monitor_trims_and_stops(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    log = RuntimeLog(home, interval=0.01)
    assert log.prepare()
    log.start()
    log.path.write_bytes(b'x' * (MAX_BYTES + 100))
    deadline = time.monotonic() + 1
    while log.path.stat().st_size > RETAIN_BYTES and time.monotonic() < deadline:
        time.sleep(0.01)
    assert log.path.stat().st_size <= RETAIN_BYTES
    worker = log._thread
    log.close()
    assert not worker.is_alive()
    assert log.report()['monitor_running'] is False


def test_foreign_config_is_never_rewritten_or_logged(tmp_path):
    home = tmp_path / 'home'
    engine = lsfg.Lsfg(str(home), tmp_path / 'state')
    engine.config_path.parent.mkdir(parents=True)
    original = 'version = 2\n[[profile]]\nname="foreign"\n'
    engine.config_path.write_text(original)
    try:
        assert engine.report()['runtime_log']['available'] is False
        assert not engine.runtime_log.path.exists()
        with pytest.raises(lsfg.LsfgError):
            engine.set_game('292030', 'Witcher', {})
        assert engine.config_path.read_text() == original
    finally:
        engine.close()


def test_report_tail_is_bounded_and_redacts_bearer_token(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    log = RuntimeLog(home)
    assert log.prepare()
    log.path.write_text('old\n' * MAX_BYTES + 'Authorization=Bearer private-bearer\n' + ('x' * 1000 + '\n') * 80)
    report = log.report()
    assert report['truncated'] is True
    assert len(report['lines']) == 60
    assert all(len(line) <= 300 for line in report['lines'])
    with log.path.open('a') as writer:
        writer.write('Authorization=Bearer private-bearer\n')
    assert 'private-bearer' not in json.dumps(log.report())


def test_retention_failure_does_not_block_profile(tmp_path):
    engine = lsfg.Lsfg(str(tmp_path / 'home'), tmp_path / 'state')
    engine.runtime_log.path.parent.mkdir(parents=True)
    victim = tmp_path / 'secret'
    victim.write_text('untouched')
    engine.runtime_log.path.symlink_to(victim)
    try:
        engine.install(payload(tmp_path / 'bundle', b'layer'), '2.0.0')
        engine.set_game('10', 'Game', {'multiplier': 3}, 'game.exe')
        config = tomllib.loads(engine.config_path.read_text())
        assert 'log_file' not in config['global']
        assert config['profile'][0]['multiplier'] == 3
        assert engine.report()['runtime_log']['retention_error'] == 'log_unavailable'
        assert victim.read_text() == 'untouched'
    finally:
        engine.close()


def test_report_hides_external_library_paths(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    log = RuntimeLog(home)
    assert log.prepare()
    log.path.write_text('failed to load "/run/media/private-user/Secret Library/lsfg-vk.dll"\n'
                        'failed /mnt/private-disk/lsfg-vk.dll\n'
                        'Authorization: Bearer private-credential\n')
    result = json.dumps(log.report())
    assert 'failed' in result
    assert 'private-user' not in result
    assert 'Secret Library' not in result
    assert 'private-disk' not in result
    assert 'private-credential' not in result


def test_malformed_owned_config_does_not_break_status(tmp_path):
    engine = lsfg.Lsfg(str(tmp_path / 'home'), tmp_path / 'state')
    engine.config_path.parent.mkdir(parents=True)
    engine.config_path.write_text(lsfg.MARKER + '\nglobal="custom"\n')
    try:
        assert engine.status()['installed'] is False
        assert engine.report()['runtime_log']['available'] is False
    finally:
        engine.close()


def test_partial_sensitive_line_is_omitted_at_report_and_retention_boundaries(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    log = RuntimeLog(home)
    assert log.prepare()
    log.path.write_text('token=' + 'private-fragment' * MAX_BYTES + '\nvalid diagnostic\n')
    assert log.report()['lines'] == ['valid diagnostic']
    log.maintain()
    assert log.path.read_text() == 'valid diagnostic\n'
    assert log.report()['lines'] == ['valid diagnostic']
