from pathlib import Path
import pytest
from upscalers import prefix_dependencies as pd
from upscalers.games import Installed

@pytest.fixture
def context(tmp_path, monkeypatch):
    library = tmp_path / 'Steam'
    root = library / 'steamapps/common/Game'
    root.mkdir(parents=True)
    compat = library / 'steamapps/compatdata/1462040'
    (compat / 'pfx/drive_c/windows/system32').mkdir(parents=True)
    (compat / 'pfx/user.reg').write_text('original')
    monkeypatch.setattr(pd.games, 'library_paths', lambda home: [library])
    monkeypatch.setattr(pd.games, 'running_under', lambda *args: False)
    monkeypatch.setattr(pd, '_guard_transaction', lambda *args: None)
    monkeypatch.setattr(pd, '_session', lambda home, proc: (1000, 1000, {'HOME': str(tmp_path), 'DISPLAY': ':1'}))
    monkeypatch.setattr(pd, '_tool', lambda *args: '/usr/bin/flatpak')
    monkeypatch.setattr(pd, '_runtime_paths', lambda *args: [])
    monkeypatch.setattr(pd.pe, 'version_strings', lambda path: {'FileVersion': '14.44.35211.0'})
    return tmp_path, Installed('1462040', 'Game', root, 4), compat

def installed(command, env, uid, gid, timeout):
    assert command[-3:] == ['-q', 'vcrun2022', 'msvcrt40']
    assert timeout == 600
    pfx = Path(env['STEAM_COMPAT_DATA_PATH']) / 'pfx'
    (pfx / 'winetricks.log').write_text('vcrun2022\nmsvcrt40\n')
    for name in ('system32/msvcp140.dll', 'system32/vcruntime140.dll', 'syswow64/msvcrt40.dll'):
        path = pfx / 'drive_c/windows' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'MZruntime')
    (pfx / 'user.reg').write_text('prepared')

def test_prepare_publish_rollback_keeps_original(context, monkeypatch):
    home, game, compat = context
    monkeypatch.setattr(pd, '_execute', installed)
    receipt = pd.prepare(str(home), game, ('vcrun2022', 'msvcrt40'))
    assert receipt['verified'] is True
    assert (compat / 'pfx/user.reg').read_text() == 'original'
    pd.publish(receipt, game.root)
    assert (compat / 'pfx/user.reg').read_text() == 'prepared'
    pd.rollback(receipt, game.root)
    assert (compat / 'pfx/user.reg').read_text() == 'original'
    pd.finish(receipt)
    assert not Path(receipt['transaction']).exists()

@pytest.mark.parametrize('failure', ['command', 'readback', 'running'])
def test_failure_never_replaces_live_prefix(context, monkeypatch, failure):
    home, game, compat = context
    def execute(*args):
        if failure == 'command':
            raise pd.DependencyError('prefix_timeout')
        if failure == 'running':
            installed(*args)
            monkeypatch.setattr(pd.games, 'running_under', lambda *a: True)
    monkeypatch.setattr(pd, '_execute', execute)
    with pytest.raises(pd.DependencyError):
        pd.prepare(str(home), game, ('vcrun2022', 'msvcrt40'))
    assert (compat / 'pfx/user.reg').read_text() == 'original'

@pytest.mark.parametrize('verbs', [('-c', 'touch /tmp/oops'), ()])
def test_rejects_arbitrary_verbs_before_execution(context, verbs):
    home, game, compat = context
    with pytest.raises(pd.DependencyError, match='prefix_unsupported'):
        pd.prepare(str(home), game, verbs)

def test_active_game_blocked_before_tool(context, monkeypatch):
    home, game, compat = context
    monkeypatch.setattr(pd.games, 'running_under', lambda *a: True)
    with pytest.raises(pd.DependencyError, match='running'):
        pd.prepare(str(home), game, ('vcrun2022',))

def test_live_prefix_absolute_symlink_rejected(context, monkeypatch):
    home, game, compat = context
    (compat / 'pfx/escape').symlink_to(compat / 'pfx/user.reg')
    with pytest.raises(pd.DependencyError, match='prefix_unsafe'):
        pd.prepare(str(home), game, ('vcrun2022',))

def test_missing_tool_has_no_transaction(context, monkeypatch):
    home, game, compat = context
    def missing(*args):
        raise pd.DependencyError('prefix_tool_unavailable')
    monkeypatch.setattr(pd, '_tool', missing)
    with pytest.raises(pd.DependencyError, match='prefix_tool_unavailable'):
        pd.prepare(str(home), game, ('vcrun2022',))
    assert list(compat.parent.iterdir()) == [compat]


def test_recovers_durable_receipt_and_finishes_idempotently(context, monkeypatch):
    home, game, compat = context
    monkeypatch.setattr(pd, '_execute', installed)
    receipt = pd.prepare(str(home), game, ('vcrun2022', 'msvcrt40'))
    assert pd.recover_pending(str(home), game) == receipt
    pd.publish(receipt, game.root)
    pd.rollback(receipt, game.root)
    pd.rollback(receipt, game.root)
    pd.finish(receipt)
    pd.finish(receipt)
    pd.rollback(receipt, game.root)


def test_old_vc_runtime_is_not_success(context, monkeypatch):
    home, game, compat = context
    monkeypatch.setattr(pd, '_execute', installed)
    monkeypatch.setattr(pd.pe, 'version_strings', lambda path: {'FileVersion': '14.28.29334.0'})
    with pytest.raises(pd.DependencyError, match='prefix_readback_failed'):
        pd.prepare(str(home), game, ('vcrun2022', 'msvcrt40'))
    assert (compat / 'pfx/user.reg').read_text() == 'original'


def test_tool_provisions_only_user_app_with_existing_remote(monkeypatch):
    calls = []
    monkeypatch.setattr(pd.shutil, 'which', lambda *a, **kw: '/usr/bin/flatpak')
    def execute(command, *args):
        calls.append(command)
        if len(calls) == 1:
            raise pd.DependencyError('prefix_install_failed')
    monkeypatch.setattr(pd, '_execute', execute)
    assert pd._tool({'PATH': '/usr/bin'}, 1000, 1000) == '/usr/bin/flatpak'
    assert calls[1][1:4] == ['remote-info', '--user', 'flathub']
    assert calls[2][1:5] == ['install', '--user', '--noninteractive', '--assumeyes']


def test_staged_child_prevents_publish(context, monkeypatch):
    home, game, compat = context
    monkeypatch.setattr(pd, '_execute', installed)
    receipt = pd.prepare(str(home), game, ('vcrun2022', 'msvcrt40'))
    def active(*args):
        raise pd.DependencyError('prefix_process_running')
    monkeypatch.setattr(pd, '_guard_transaction', active)
    with pytest.raises(pd.DependencyError, match='prefix_process_running'):
        pd.publish(receipt, game.root)
    assert (compat / 'pfx/user.reg').read_text() == 'original'


def test_selected_runtime_receives_invocation_only_write_permission(context, monkeypatch):
    home, game, compat = context
    runtime = home / 'OtherSD/steamapps/common/SteamLinuxRuntime_sniper'
    monkeypatch.setattr(pd, '_runtime_paths', lambda *args: [runtime])
    def execute(command, *args):
        assert f'--filesystem={runtime}:rw' in command
        assert 'override' not in command
        return installed(command, *args)
    monkeypatch.setattr(pd, '_execute', execute)
    pd.prepare(str(home), game, ('vcrun2022', 'msvcrt40'))


def test_first_receipt_write_failure_leaves_no_orphan_and_allows_retry(context, monkeypatch):
    home, game, compat = context
    save = pd._save
    calls = 0
    def full(receipt):
        nonlocal calls
        calls += 1
        if calls == 1:
            (Path(receipt['transaction']) / 'receipt.tmp').write_text('{')
            raise OSError(28, 'No space left')
        return save(receipt)
    monkeypatch.setattr(pd, '_save', full)
    monkeypatch.setattr(pd, '_execute', installed)
    with pytest.raises(pd.DependencyError, match='prefix_transaction_failed'):
        pd.prepare(str(home), game, ('vcrun2022', 'msvcrt40'))
    assert list(compat.parent.iterdir()) == [compat]
    assert pd.prepare(str(home), game, ('vcrun2022', 'msvcrt40'))['state'] == 'prepared'


def test_runtime_discovery_uses_installed_resolver_and_readonly_libraries(tmp_path, monkeypatch):
    import json
    steam = tmp_path / 'Steam'
    sd = tmp_path / 'SD'
    proton = sd / 'steamapps/common/Proton 11'
    runtime = sd / 'steamapps/common/SteamLinuxRuntime_sniper'
    proton.mkdir(parents=True)
    runtime.mkdir(parents=True)
    (proton / 'proton').write_text('runtime entry')
    monkeypatch.setattr(pd.games, 'steam_roots', lambda home: [steam])
    monkeypatch.setattr(pd.games, 'library_paths', lambda home: [steam, sd])
    def query(command, env, uid, gid, timeout, capture=False):
        assert f'--filesystem={sd}:ro' in command
        assert '--command=python3' in command
        assert capture and timeout == 30
        compile(command[-3], '<runtime-query>', 'exec')
        return json.dumps([str(proton), str(runtime)])
    monkeypatch.setattr(pd, '_execute', query)
    assert pd._runtime_paths(str(tmp_path), '1462040', '/usr/bin/flatpak', {}, 1000, 1000) == [proton, runtime]


def test_runtime_discovery_rejects_paths_outside_steam(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(pd.games, 'steam_roots', lambda home: [tmp_path / 'Steam'])
    monkeypatch.setattr(pd.games, 'library_paths', lambda home: [tmp_path / 'Steam'])
    monkeypatch.setattr(pd, '_execute', lambda *a, **kw: json.dumps([str(tmp_path)]))
    with pytest.raises(pd.DependencyError, match='prefix_runtime_unavailable'):
        pd._runtime_paths(str(tmp_path), '1462040', '/usr/bin/flatpak', {}, 1000, 1000)


@pytest.mark.parametrize('available', ['installed', '--user', '--system', None])
def test_tool_selects_existing_scope_and_keeps_queries_unprivileged(monkeypatch, available):
    calls = []
    monkeypatch.setattr(pd.shutil, 'which', lambda *a, **kw: '/usr/bin/flatpak')
    monkeypatch.setattr(pd.os, 'geteuid', lambda: 0)
    def execute(command, env, uid, gid, timeout):
        calls.append((command, uid, gid, env))
        if command[1] == 'info' and len(calls) == 1 and available != 'installed':
            raise pd.DependencyError('prefix_install_failed')
        if command[1] == 'remote-info' and command[2] != available:
            raise pd.DependencyError('prefix_install_failed')
    monkeypatch.setattr(pd, '_execute', execute)
    if available is None:
        with pytest.raises(pd.DependencyError, match='prefix_tool_unavailable'):
            pd._tool({'PATH': '/usr/bin'}, 1000, 1000)
    else:
        assert pd._tool({'PATH': '/usr/bin'}, 1000, 1000) == '/usr/bin/flatpak'
    installs = [c for c in calls if c[0][1] == 'install']
    assert len(installs) == int(available in ('--user', '--system'))
    if installs:
        command, uid, gid, env = installs[0]
        assert command[2:] == [available, '--noninteractive', '--assumeyes', 'flathub', pd._FLATPAK]
        assert (uid, gid) == ((0, 0) if available == '--system' else (1000, 1000))
        if available == '--system':
            assert 'DBUS_SESSION_BUS_ADDRESS' not in env
    assert all(c[1:3] == (1000, 1000) for c in calls if c[0][1] != 'install')


@pytest.mark.parametrize('scope', ['--user', '--system'])
def test_tool_install_failure_does_not_try_other_scope(monkeypatch, scope):
    calls = []
    monkeypatch.setattr(pd.shutil, 'which', lambda *a, **kw: '/usr/bin/flatpak')
    monkeypatch.setattr(pd.os, 'geteuid', lambda: 0)
    def execute(command, *args):
        calls.append(command)
        if command[1] == 'info' or (command[1] == 'remote-info' and command[2] != scope):
            raise pd.DependencyError('prefix_install_failed')
        if command[1] == 'install':
            raise pd.DependencyError('prefix_timeout')
    monkeypatch.setattr(pd, '_execute', execute)
    with pytest.raises(pd.DependencyError, match='prefix_timeout'):
        pd._tool({'PATH': '/usr/bin'}, 1000, 1000)
    assert calls[-1][1:3] == ['install', scope]
    assert sum(c[1] == 'install' for c in calls) == 1


def test_system_tool_install_without_root_fails_without_installing(monkeypatch):
    calls = []
    monkeypatch.setattr(pd.shutil, 'which', lambda *a, **kw: '/usr/bin/flatpak')
    monkeypatch.setattr(pd.os, 'geteuid', lambda: 1000)
    def execute(command, *args):
        calls.append(command)
        if command[1] == 'info' or '--user' in command:
            raise pd.DependencyError('prefix_install_failed')
    monkeypatch.setattr(pd, '_execute', execute)
    with pytest.raises(pd.DependencyError, match='prefix_tool_unavailable'):
        pd._tool({'PATH': '/usr/bin'}, 1000, 1000)
    assert not any(c[1] == 'install' for c in calls)
