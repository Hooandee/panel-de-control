"""Transactional, allowlisted Windows prerequisites for native Steam installations."""
from __future__ import annotations

import json
import os
import pwd
import re
import shutil
import signal
import subprocess
from pathlib import Path

from . import games, pe

_ALLOWED = {'vcrun2022', 'msvcrt40'}
_DLLS = {'vcrun2022': ('system32/msvcp140.dll', 'system32/vcruntime140.dll'), 'msvcrt40': ('syswow64/msvcrt40.dll',)}
_FLATPAK = 'com.github.Matoking.protontricks'


class DependencyError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _execute(command, env, uid, gid, timeout, capture=False):
    kwargs = {'env': env, 'stdin': subprocess.DEVNULL, 'stdout': subprocess.PIPE if capture else subprocess.DEVNULL,
              'stderr': subprocess.DEVNULL, 'start_new_session': True}
    if os.geteuid() == 0:
        kwargs.update(user=uid, group=gid, extra_groups=[])
    elif os.geteuid() != uid:
        raise DependencyError('prefix_user_unavailable')
    try:
        process = subprocess.Popen(command, **kwargs)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
            raise DependencyError('prefix_timeout') from None
    except OSError:
        raise DependencyError('prefix_tool_unavailable') from None
    if code:
        raise DependencyError('prefix_install_failed')
    if capture:
        return process.stdout.read(16384).decode('utf-8')


def _session(home, proc):
    owner = Path(home).stat().st_uid
    account = pwd.getpwuid(owner)
    if owner == 0:
        raise DependencyError('prefix_user_unavailable')
    env = {'HOME': home, 'USER': account.pw_name, 'LOGNAME': account.pw_name,
           'PATH': '/usr/local/bin:/usr/bin:/bin', 'XDG_RUNTIME_DIR': f'/run/user/{owner}',
           'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{owner}/bus'}
    for process in Path(proc).iterdir():
        if not process.name.isdecimal():
            continue
        try:
            if process.stat().st_uid != owner:
                continue
            values = dict(item.split(b'=', 1) for item in (process / 'environ').read_bytes().split(b'\0') if b'=' in item)
            display = values.get(b'DISPLAY', b'').decode()
            if re.fullmatch(r':[0-9]+(?:\.[0-9]+)?', display):
                env['DISPLAY'] = display
                auth = values.get(b'XAUTHORITY', b'').decode()
                if auth and Path(auth).is_file() and Path(auth).stat().st_uid == owner:
                    env['XAUTHORITY'] = auth
                return owner, account.pw_gid, env
        except (OSError, UnicodeError):
            continue
    raise DependencyError('prefix_display_unavailable')


def _tool(env, uid, gid, logger=None):
    executable = shutil.which('flatpak', path=env['PATH'])
    if not executable:
        raise DependencyError('prefix_tool_unavailable')
    try:
        _execute([executable, 'info', _FLATPAK], env, uid, gid, 15)
        return executable
    except DependencyError:
        pass
    scope = None
    for candidate in ('--user', '--system'):
        try:
            _execute([executable, 'remote-info', candidate, 'flathub', _FLATPAK], env, uid, gid, 30)
        except DependencyError as error:
            if logger:
                logger.warning('Upscaler prerequisite tool probe: scope=%s code=%s', candidate, error.code)
            continue
        scope = candidate
        break
    if scope is None:
        raise DependencyError('prefix_tool_unavailable')
    install_env, install_uid, install_gid = env, uid, gid
    if scope == '--system':
        if os.geteuid() != 0:
            raise DependencyError('prefix_tool_unavailable')
        install_env = {'PATH': env['PATH'], 'HOME': pwd.getpwuid(0).pw_dir, 'USER': 'root', 'LOGNAME': 'root'}
        install_uid = install_gid = 0
    if logger:
        logger.info('Upscaler prerequisite tool install: scope=%s app=%s', scope, _FLATPAK)
    try:
        _execute([executable, 'install', scope, '--noninteractive', '--assumeyes', 'flathub', _FLATPAK],
                 install_env, install_uid, install_gid, 600)
        _execute([executable, 'info', _FLATPAK], env, uid, gid, 15)
    except DependencyError as error:
        if logger:
            logger.warning('Upscaler prerequisite tool install failed: scope=%s code=%s', scope, error.code)
        raise
    return executable


_RUNTIME_QUERY = """
import json, sys
from pathlib import Path
from protontricks.steam import get_steam_apps, get_steam_lib_paths, find_proton_app
root = Path(sys.argv[1])
apps = get_steam_apps(steam_root=root, steam_path=root, steam_lib_paths=get_steam_lib_paths(root))
proton = find_proton_app(steam_path=root, steam_apps=apps, appid=int(sys.argv[2]))
if not proton or not proton.is_proton_ready:
    raise SystemExit(2)
paths = [str(proton.install_path)]
if proton.required_tool_appid:
    if not proton.required_tool_app:
        raise SystemExit(3)
    paths.append(str(proton.required_tool_app.install_path))
print(json.dumps(paths))
"""


def _runtime_paths(home, appid, executable, env, uid, gid):
    roots = games.steam_roots(home)
    if len(roots) != 1:
        raise DependencyError('prefix_runtime_ambiguous')
    libraries = games.library_paths(home)
    command = [executable, 'run', *[f'--filesystem={library}:ro' for library in libraries],
               '--command=python3', _FLATPAK, '-c', _RUNTIME_QUERY, str(roots[0]), appid]
    try:
        paths = json.loads(_execute(command, env, uid, gid, 30, capture=True))
        if not isinstance(paths, list) or not 1 <= len(paths) <= 2:
            raise ValueError()
        allowed = [library.resolve() / 'steamapps/common' for library in libraries]
        allowed += [roots[0].resolve() / 'compatibilitytools.d',
                    Path('/usr/share/steam/compatibilitytools.d'),
                    Path('/usr/local/share/steam/compatibilitytools.d')]
        result = []
        for raw in paths:
            path = Path(raw).resolve(strict=True)
            if not path.is_dir() or not any(path.is_relative_to(base) and path != base for base in allowed):
                raise ValueError()
            result.append(path)
        if not (result[0] / 'proton').is_file():
            raise ValueError()
        return result
    except (DependencyError, OSError, ValueError, TypeError):
        raise DependencyError('prefix_runtime_unavailable') from None


def _guard(root, proc):
    if games.running_under(Path(root), proc):
        raise DependencyError('running')


def _guard_transaction(transaction, proc='/proc'):
    if not Path(proc).is_dir():
        raise DependencyError('prefix_process_state_unavailable')
    needle = str(transaction).encode()
    owner = transaction.stat().st_uid
    for process in Path(proc).iterdir():
        if not process.name.isdecimal():
            continue
        try:
            if process.stat().st_uid != owner:
                continue
            environment = (process / 'environ').read_bytes()
            command = (process / 'cmdline').read_bytes()
            if needle in environment or needle in command:
                raise DependencyError('prefix_process_running')
        except PermissionError:
            raise DependencyError('prefix_process_state_unavailable') from None
        except FileNotFoundError:
            continue


def _paths(receipt):
    appid = str(receipt.get('appid', ''))
    compat = Path(receipt.get('compatdata', ''))
    transaction = Path(receipt.get('transaction', ''))
    if (not appid.isdecimal() or compat.name != appid or compat.parent.name != 'compatdata'
            or transaction != compat.parent / f'.pdc-dependencies-{appid}'
            or transaction.is_symlink() or compat.is_symlink()):
        raise DependencyError('prefix_receipt_invalid')
    return compat, transaction


def _save(receipt):
    _, transaction = _paths(receipt)
    temporary = transaction / 'receipt.tmp'
    with temporary.open('w') as stream:
        json.dump(receipt, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(transaction / 'receipt.json')


def _verify(pfx, dependencies):
    try:
        verbs = set((pfx / 'winetricks.log').read_text().splitlines())
        if 'vcrun2022' in dependencies:
            version = pe.version_strings(str(pfx / 'drive_c/windows/system32/msvcp140.dll')).get('FileVersion', '')
            numbers = tuple(int(part) for part in re.findall(r'\d+', version)[:4])
            if numbers < (14, 44):
                return False
        return all(verb in verbs and all((pfx / 'drive_c/windows' / name).is_file()
                   and (pfx / 'drive_c/windows' / name).stat().st_size > 2
                   for name in _DLLS[verb]) for verb in dependencies)
    except OSError:
        return False


def prepare(home: str, installed: games.Installed, dependencies, logger=None, proc='/proc'):
    dependencies = tuple(dependencies)
    if not dependencies or any(verb not in _ALLOWED for verb in dependencies):
        raise DependencyError('prefix_unsupported')
    if installed.shortcut or installed.native or not installed.appid.isdecimal():
        raise DependencyError('prefix_unavailable')
    _guard(installed.root, proc)
    candidates = []
    for library in games.library_paths(home):
        compat = library / 'steamapps/compatdata' / installed.appid
        if (compat / 'pfx').is_dir():
            candidates.append(compat)
    # A game moved between libraries can leave its old prefix behind; Steam uses the one beside the game.
    beside = [compat for compat in candidates if Path(installed.root).is_relative_to(compat.parent.parent.parent)]
    if len(candidates) > 1 and len(beside) == 1:
        candidates = beside
    if len(candidates) != 1:
        raise DependencyError('prefix_ambiguous' if candidates else 'prefix_unavailable')
    compat = candidates[0]
    transaction = compat.parent / f'.pdc-dependencies-{installed.appid}'
    receipt = {'appid': installed.appid, 'compatdata': str(compat), 'transaction': str(transaction),
               'dependencies': list(dependencies), 'state': 'preparing', 'verified': False}
    _paths(receipt)
    if (compat / 'pfx').is_symlink():
        raise DependencyError('prefix_unsafe')
    if transaction.exists():
        stale = _recovered(compat, transaction)
        if stale.get('state') == 'published':
            raise DependencyError('prefix_recovery_required')
        _guard_transaction(transaction, proc)
        shutil.rmtree(transaction)
    if _verify(compat / 'pfx', dependencies):
        return None
    uid, gid, env = _session(home, proc)
    executable = _tool(env, uid, gid, logger)
    runtimes = _runtime_paths(home, installed.appid, executable, env, uid, gid)
    try:
        transaction.mkdir(mode=0o700)
    except FileExistsError:
        raise DependencyError('prefix_recovery_required') from None
    try:
        _save(receipt)
    except OSError:
        for name in ('receipt.tmp', 'receipt.json'):
            (transaction / name).unlink(missing_ok=True)
        transaction.rmdir()
        raise DependencyError('prefix_transaction_failed') from None
    try:
        staged = transaction / 'compat'
        shutil.copytree(compat, staged, symlinks=True)
        # Absolute links into the live prefix would escape staging and mutate originals.
        for directory, dirs, files in os.walk(staged, followlinks=False):
            for name in dirs + files:
                path = Path(directory) / name
                if path.is_symlink():
                    if path.resolve().is_relative_to(compat.resolve()):
                        raise DependencyError('prefix_unsafe')
                if os.geteuid() == 0:
                    os.chown(path, uid, gid, follow_symlinks=False)
            if os.geteuid() == 0:
                os.chown(directory, uid, gid)
        if os.geteuid() == 0:
            os.chown(transaction, uid, gid)
        env['STEAM_COMPAT_DATA_PATH'] = str(staged)
        command = [executable, 'run', f'--filesystem={compat.parent.parent.parent}',
                   *[f'--filesystem={runtime}:rw' for runtime in runtimes],
                   f'--env=STEAM_COMPAT_DATA_PATH={staged}', f'--env=DISPLAY={env["DISPLAY"]}',
                   _FLATPAK, installed.appid, '-q', *dependencies]
        _guard(installed.root, proc)
        _execute(command, env, uid, gid, 600)
        if not _verify(staged / 'pfx', dependencies):
            raise DependencyError('prefix_readback_failed')
        _guard(installed.root, proc)
        _guard_transaction(transaction, proc)
        receipt.update(state='prepared', verified=True)
        _save(receipt)
        if logger:
            logger.info('Upscaler Windows prerequisites prepared: appid=%s', installed.appid)
        return receipt
    except Exception as error:
        receipt['state'] = 'failed'
        _save(receipt)
        if logger:
            logger.warning('Upscaler Windows prerequisites failed: %s', getattr(error, 'code', type(error).__name__))
        # Retain failed staging: Flatpak services may outlive their command after a timeout.
        raise


def publish(receipt, game_root, proc='/proc'):
    compat, transaction = _paths(receipt)
    _guard(game_root, proc)
    if receipt.get('state') != 'prepared' or not _verify(transaction / 'compat/pfx', receipt['dependencies']):
        raise DependencyError('prefix_readback_failed')
    _guard_transaction(transaction, proc)
    receipt['state'] = 'publishing'
    _save(receipt)
    (compat / 'pfx').rename(transaction / 'original-pfx')
    try:
        (transaction / 'compat/pfx').rename(compat / 'pfx')
    except OSError:
        (transaction / 'original-pfx').rename(compat / 'pfx')
        raise
    receipt['state'] = 'published'
    _save(receipt)
    return receipt


def rollback(receipt, game_root, proc='/proc'):
    compat, transaction = _paths(receipt)
    _guard(game_root, proc)
    if not transaction.exists() and receipt.get('state') == 'rolled_back':
        return receipt
    _guard_transaction(transaction, proc)
    original = transaction / 'original-pfx'
    if original.is_dir():
        if (compat / 'pfx').exists():
            (compat / 'pfx').rename(transaction / 'rejected-pfx')
        original.rename(compat / 'pfx')
    receipt['state'] = 'rolled_back'
    _save(receipt)
    return receipt


def finish(receipt, proc='/proc'):
    _, transaction = _paths(receipt)
    if receipt.get('state') not in ('published', 'rolled_back'):
        raise DependencyError('prefix_recovery_required')
    if transaction.exists():
        _guard_transaction(transaction, proc)
        shutil.rmtree(transaction)


def recover_pending(home: str, installed: games.Installed):
    for library in games.library_paths(home):
        compat = library / 'steamapps/compatdata' / installed.appid
        transaction = compat.parent / f'.pdc-dependencies-{installed.appid}'
        if not transaction.exists():
            continue
        if transaction.is_symlink():
            raise DependencyError('prefix_recovery_required')
        return _recovered(compat, transaction)
    return None


def _recovered(compat, transaction):
    """The transaction's receipt, or, when it was never written or got lost, the state its folders prove."""
    for name in ('receipt.json', 'receipt.tmp'):
        try:
            receipt = json.loads((transaction / name).read_text())
            if _paths(receipt) == (compat, transaction):
                return receipt
        except (OSError, ValueError, TypeError, AttributeError, DependencyError):
            continue
    appid = compat.name
    receipt = {'appid': appid, 'compatdata': str(compat), 'transaction': str(transaction),
               'dependencies': [], 'verified': False}
    original = transaction / 'original-pfx'
    if original.is_dir() and not original.is_symlink():
        if not (compat / 'pfx').exists():
            original.rename(compat / 'pfx')
            receipt['state'] = 'rolled_back'
        else:
            receipt['state'] = 'published'
    else:
        receipt['state'] = 'rolled_back'
    _save(receipt)
    return receipt


def status(home: str, installed, dependencies) -> dict:
    requested = list(dict.fromkeys(verb if verb in _ALLOWED else 'unsupported' for verb in dependencies))
    result = {'state': 'unknown', 'dependencies': [{'id': verb, 'state': 'unknown'} for verb in requested]}
    if installed is None or installed.shortcut or installed.native or 'unsupported' in requested:
        return result
    try:
        if recover_pending(home, installed):
            state = 'pending'
        else:
            prefixes = [library / 'steamapps/compatdata' / installed.appid / 'pfx'
                        for library in games.library_paths(home)
                        if (library / 'steamapps/compatdata' / installed.appid / 'pfx').is_dir()]
            if len(prefixes) > 1 or any(path.is_symlink() for path in prefixes):
                return result
            if not prefixes:
                state = 'missing'
            else:
                result['dependencies'] = [{'id': verb, 'state': 'ready' if _verify(prefixes[0], (verb,)) else 'missing'}
                                          for verb in requested]
                result['state'] = 'ready' if all(item['state'] == 'ready' for item in result['dependencies']) else 'missing'
                return result
        result['state'] = state
        for item in result['dependencies']:
            item['state'] = state
    except (DependencyError, OSError, ValueError, TypeError):
        pass
    return result
