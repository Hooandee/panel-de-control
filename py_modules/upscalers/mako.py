"""Private per-game MAKO renderer configuration and verified runtime installation."""

import fcntl
import hashlib
import json
import logging
import math
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
from pathlib import Path

from . import games, ownership
from .assets import sha256
from .catalog import Asset

VERSION = "4.6.0"
# Existing Steam launch receipts reference this slot; upgrades must preserve its path.
INSTALL_SLOT = "4.6.0"
ASSET = Asset("mako-render-4.6.0", "MAKO-Renderer-v4.6.0-linux.tar.xz",
              "66224414e2d94f7cb019226735b3b6d26b9be7103c5334250522f7260213be56", 2890224,
              ("https://github.com/eugeniosegala/MAKO/releases/download/render-v4.6.0/MAKO-Renderer-v4.6.0-linux.tar.xz",))
PAYLOAD = ("bin/mako-launch", "bin/mako-cli", "bin/mako-vrr-lease",
           "lib/libmako-render.so", "lib32/libmako-render.so",
           "share/mako-render/vulkan/implicit_layer.d/VkLayer_MAKO_render.json",
           "share/mako-render/vulkan/implicit_layer.d/VkLayer_MAKO_render.x86.json")
FLOW = {"quality": 1.0, "balanced": 0.75, "performance": 0.5, "fastest": 0.25}
DEFAULTS = {"enabled": True, "mode": "fixed", "multiplier": 2, "target_fps": 120,
            "max_multiplier": 3, "flow": "quality", "performance": False,
            "scaling_enabled": False, "scaling_factor": 1.5, "scaling_sharpness": 0.8}
LOG = logging.getLogger(__name__)
MAX_JSON = 128 * 1024


class MakoError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _json(path):
    try:
        if path.is_symlink() or path.stat().st_size > MAX_JSON:
            return {}
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _appid(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,20}", value):
        raise MakoError("mako_appid")
    return value


def _options(config):
    if not isinstance(config, dict) or set(config) - DEFAULTS.keys():
        raise MakoError("mako_options")
    result = DEFAULTS | config
    for key, lo, hi in (("multiplier", 2, 5), ("target_fps", 30, 240), ("max_multiplier", 2, 5)):
        if type(result[key]) is not int or not lo <= result[key] <= hi:
            raise MakoError("mako_options")
    if (not isinstance(result['mode'], str) or not isinstance(result['flow'], str)
            or type(result['enabled']) is not bool or type(result['performance']) is not bool
            or result['mode'] not in ('fixed', 'adaptive') or result['flow'] not in FLOW):
        raise MakoError("mako_options")
    if type(result['scaling_enabled']) is not bool:
        raise MakoError("mako_options")
    for key, lo, hi in (("scaling_factor", 1, 2), ("scaling_sharpness", 0, 1)):
        if type(result[key]) not in (int, float) or not math.isfinite(result[key]) or not lo <= result[key] <= hi:
            raise MakoError("mako_options")
    return result


class Mako:
    def __init__(self, home: str, state_dir: Path):
        self.home = Path(home)
        self.prefix = self.home / '.local/share/panel-de-control/mako' / INSTALL_SLOT
        self.config_root = self.home / '.config/panel-de-control/mako'
        self.manifest_path = Path(state_dir) / 'mako.json'
        self._lock = threading.RLock()
        self._namespace_candidates = {}
        self._namespace_scan_at = float("-inf")

    def _state(self):
        state = _json(self.manifest_path)
        return {**state, 'profiles': state.get('profiles', {}) if isinstance(state.get('profiles'), dict) else {}}

    def _safe(self, path):
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise MakoError('mako_conflict')
            if parent == self.home or parent == self.manifest_path.parent:
                break

    def _write(self, path, content):
        self._safe(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix='.mako-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as handle:
                handle.write(content)
            os.replace(temp, path)
            if self.home in path.parents:
                ownership.own_with_parents(self.home, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def _save(self, state):
        self._write(self.manifest_path, json.dumps(state, separators=(',', ':')))

    def _persist_files(self, changes, state):
        previous = {}
        for path in (*changes, self.manifest_path):
            self._safe(path)
            if path.exists() and path.stat().st_size > MAX_JSON:
                raise MakoError('mako_conflict')
            previous[path] = path.read_text() if path.exists() else None
        try:
            for path, content in changes.items():
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    self._write(path, content)
            self._save(state)
        except (OSError, MakoError) as error:
            failed = False
            for path, content in previous.items():
                try:
                    if content is None:
                        path.unlink(missing_ok=True)
                    elif not path.exists() or path.read_text() != content:
                        Mako._write(self, path, content)
                except (OSError, MakoError):
                    failed = True
            raise MakoError('mako_restore_failed' if failed else 'mako_write_failed') from error

    def _event(self, state, action, appid=None, code=None):
        events = state.get('events', [])
        state['events'] = (events[-31:] if isinstance(events, list) else []) + [
            {'at': int(time.time()), 'action': action, 'appid': appid, 'code': code}]
        LOG.info('MAKO action=%s appid=%s code=%s', action, appid, code)

    def _dll(self):
        for library in games.library_paths(str(self.home)):
            path = library / 'steamapps/common/Lossless Scaling/Lossless.dll'
            if path.is_file():
                return path
        return None

    @staticmethod
    def _signature(path):
        if path is None:
            return None
        try:
            stat = path.stat()
            return {'size': stat.st_size, 'mtime': stat.st_mtime_ns, 'inode': stat.st_ino}
        except OSError:
            return None

    def _installed(self, state):
        files = state.get('files', {})
        return bool(files) and all((self.prefix / name).is_file() and not (self.prefix / name).is_symlink()
                                   for name in PAYLOAD) and set(files) == set(PAYLOAD)

    def status(self):
        with self._lock:
            state = self._state()
            installed = self._installed(state)
            dll = self._dll()
            checked = state.get('inspection', {})
            if not isinstance(checked, dict):
                checked = {}
            compatible = bool(checked.get('compatible') and checked.get('signature') == self._signature(dll))
            supported = platform.machine().lower() in ('x86_64', 'amd64')
            reason = ('mako_arch' if not supported else 'mako_not_installed' if not installed else
                      'mako_dll_missing' if not dll else None if compatible else 'mako_unchecked')
            profiles = {}
            for key, value in list(state['profiles'].items())[:256]:
                if not isinstance(value, dict) or not re.fullmatch(r'[0-9]{1,20}', key):
                    continue
                try:
                    profiles[key] = _options({field: value[field] for field in DEFAULTS if field in value})
                except MakoError:
                    continue
            return {'installed': installed, 'ready': reason is None, 'reason': reason,
                    'supported': supported, 'spatial_ready': supported and installed, 'dll': bool(dll), 'version': state.get('version', VERSION) if installed else None,
                    'foreign': (self.home / '.local/bin/mako-run').exists() or (self.home / '.local/bin/mako-launch').exists(),
                    'profiles': profiles}

    def install(self, cache, progress=None, cancelled=None, *, asset=None, version=None, before_commit=None):
        asset = asset or ASSET
        version = version or VERSION
        progress = progress or (lambda size: None)
        cancelled = cancelled or (lambda: False)
        with self._lock:
            if platform.machine().lower() not in ('x86_64', 'amd64'):
                raise MakoError('mako_arch')
            state = self._state()
            upgrading = self._installed(state)
            if upgrading:
                self._verify_install(state)
                if state.get('version', VERSION) == version:
                    return self.status()
            self._safe(self.prefix)
            if self.prefix.exists() and not upgrading:
                raise MakoError('mako_conflict')
            archive = cache.ensure(asset, progress, cancelled)
            if sha256(archive) != asset.sha256:
                raise MakoError('mako_checksum')
            self.prefix.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix='.mako-', dir=self.prefix.parent))
            published = False
            committed = False
            backup = staging.with_name(staging.name + "-previous")
            try:
                found = set()
                with tarfile.open(archive, 'r:xz') as handle:
                    for member in handle:
                        name = str(Path(member.name))
                        if Path(name).is_absolute() or '..' in Path(name).parts or member.issym() or member.islnk():
                            raise MakoError('mako_archive')
                        if name not in PAYLOAD:
                            continue
                        if name in found or not member.isfile() or not 0 < member.size <= 16 * 1024 * 1024:
                            raise MakoError('mako_archive')
                        if cancelled():
                            raise MakoError('cancelled')
                        target = staging / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with handle.extractfile(member) as source, target.open('wb') as dest:
                            shutil.copyfileobj(source, dest)
                        target.chmod(0o755 if name.startswith('bin/') else 0o644)
                        found.add(name)
                if found != set(PAYLOAD):
                    raise MakoError('mako_archive')
                files = {name: sha256(staging / name) for name in PAYLOAD}
                if upgrading:
                    state.pop('inspection', None)
                    if any(profile.get('enabled', True) for profile in state['profiles'].values()):
                        self._inspect(state, self._dll(), prefix=staging)
                    for appid, profile in {**state.get('paused', {}), **state['profiles']}.items():
                        if not re.fullmatch(r'[0-9]{1,20}', appid):
                            raise MakoError('mako_conflict')
                        config = self.config_root / appid / 'conf.toml'
                        self._safe(config)
                        if config.stat().st_size > MAX_JSON or sha256(config) != profile.get('hash'):
                            raise MakoError('mako_conflict')
                        self._validate(config.read_text(), prefix=staging)
                if before_commit:
                    before_commit()
                if upgrading:
                    self.prefix.rename(backup)
                staging.rename(self.prefix)
                published = True
                for name in PAYLOAD:
                    ownership.own_with_parents(self.home, self.prefix / name)
                state.update(files=files, version=version, asset_sha256=asset.sha256)
                self._event(state, 'update' if upgrading else 'install')
                self._persist_files({}, state)
                committed = True
            except (tarfile.TarError, EOFError, OSError, MakoError) as error:
                try:
                    if published:
                        self.prefix.rename(staging)
                    if backup.exists():
                        backup.rename(self.prefix)
                except OSError as restore_error:
                    LOG.error('MAKO action=install code=mako_restore_failed')
                    raise MakoError('mako_restore_failed') from restore_error
                code = error.code if isinstance(error, MakoError) else 'mako_write_failed' if isinstance(error, OSError) else 'mako_archive'
                LOG.error('MAKO action=install code=%s', code)
                raise MakoError(code) from error
            finally:
                if staging.exists():
                    try:
                        shutil.rmtree(staging)
                    except OSError:
                        LOG.warning("MAKO action=install code=staging_cleanup_failed")
                if backup.exists() and committed:
                    try:
                        shutil.rmtree(backup)
                    except OSError:
                        LOG.warning("MAKO action=update code=backup_cleanup_failed")
            return self.status()

    def _verify_install(self, state):
        if not self._installed(state):
            raise MakoError('mako_not_installed')
        for name in PAYLOAD:
            self._safe(self.prefix / name)
            if sha256(self.prefix / name) != state['files'][name]:
                raise MakoError('mako_conflict')

    def _inspect(self, state, dll, *, prefix=None):
        if dll is None:
            raise MakoError('mako_dll_missing')
        with tempfile.TemporaryFile() as output:
            try:
                result = subprocess.run([str((prefix or self.prefix) / 'bin/mako-cli'), 'inspect-dll', '--dll', str(dll), '--lsfg'],
                                        stdout=output, stderr=subprocess.DEVNULL, timeout=15, check=False)
            except subprocess.TimeoutExpired as error:
                raise MakoError('mako_inspection_timeout') from error
            except OSError as error:
                raise MakoError('mako_inspection_failed') from error
            output.seek(0)
            try:
                data = json.loads(output.read(8192))
            except (ValueError, UnicodeError):
                data = {}
            if result.returncode != 0 or not isinstance(data, dict) or data.get('compatible') is not True:
                raise MakoError('mako_dll_incompatible')
        state['inspection'] = {'compatible': True, 'signature': self._signature(dll), 'sha256': sha256(dll)}

    def _validate(self, content, *, prefix=None):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml') as config, tempfile.TemporaryFile() as output:
            config.write(content)
            config.flush()
            try:
                result = subprocess.run([str((prefix or self.prefix) / 'bin/mako-cli'), 'validate', '--config', config.name],
                                        stdout=output, stderr=subprocess.DEVNULL, timeout=15, check=False)
            except subprocess.TimeoutExpired as error:
                raise MakoError('mako_validation_timeout') from error
            except OSError as error:
                raise MakoError('mako_validation_failed') from error
            if result.returncode != 0:
                raise MakoError('mako_config_invalid')

    def set_game(self, appid, name, config, exe=None):
        appid = _appid(appid)
        with self._lock:
            state = self._state()
            path = self.config_root / appid / 'conf.toml'
            launcher_config = path.parent / 'launcher.conf'
            try:
                self._safe(path)
                self._safe(launcher_config)
                paused = state.get('paused', {})
                if not isinstance(paused, dict):
                    paused = {}
                previous = state['profiles'].get(appid, paused.get(appid, {}))
                if not isinstance(previous, dict):
                    raise MakoError('mako_conflict')
                current = state['profiles'].get(appid, {})
                if config is not None and not isinstance(config, dict):
                    raise MakoError('mako_options')
                options = _options({key: current[key] for key in DEFAULTS if key in current} | config) if config is not None else None
                if options and not options['enabled'] and not options['scaling_enabled']:
                    options = None
                for owned, key in ((path, 'hash'), (launcher_config, 'launcher_hash')):
                    if owned.exists() and (not previous.get(key) or sha256(owned) != previous[key]):
                        raise MakoError('mako_conflict')
                if options is None:
                    changes = {}
                    if path.exists():
                        if path.stat().st_size > MAX_JSON:
                            raise MakoError('mako_conflict')
                        content = path.read_text().replace('frame_generation_enabled = true', 'frame_generation_enabled = false').replace('scaling_enabled = true', 'scaling_enabled = false')
                        changes[path] = content
                        paused[appid] = {'hash': hashlib.sha256(content.encode()).hexdigest(), 'launcher_hash': previous.get('launcher_hash')}
                    state['paused'] = paused
                    state['profiles'].pop(appid, None)
                    self._event(state, 'remove', appid)
                    self._persist_files(changes, state)
                    return {'env': {}, 'wrappers': [], 'profile': None}
                if platform.machine().lower() not in ('x86_64', 'amd64'):
                    raise MakoError('mako_arch')
                if appid not in state['profiles'] and len(state['profiles']) + len(paused) >= 256 and appid not in paused:
                    raise MakoError('mako_profile_limit')
                self._verify_install(state)
                dll = self._dll() if options['enabled'] else None
                if options['enabled']:
                    self._inspect(state, dll)
                def boolean(value):
                    return str(value).lower()
                content = ('version = 2\n[global]\ndll = ' + json.dumps(str(dll) if dll else '') + '\nallow_fp16 = true\n'
                           '[[profile]]\nname = "pdc-' + appid + '"\nactive_in = []\n'
                           f'frame_generation_provisioned = {boolean(options["enabled"])}\n'
                           f'scaling_enabled = {boolean(options["scaling_enabled"])}\n'
                           f'frame_generation_enabled = {boolean(options["enabled"])}\n'
                           f'multiplier = {options["multiplier"]}\nadaptive = {boolean(options["mode"] == "adaptive")}\n'
                           f'target_fps = {options["target_fps"]}\nadaptive_max_multiplier = {options["max_multiplier"]}\n'
                           f'flow_scale = {FLOW[options["flow"]]}\nperformance_mode = {boolean(options["performance"])}\n')
                if options['scaling_enabled']:
                    content += ('scaling_method = "mako"\nscaling_supersampling = false\n'
                                f'scaling_factor = {options["scaling_factor"]}\n'
                                f'scaling_sharpness = {options["scaling_sharpness"]}\n')
                self._validate(content)
                launcher_content = '# Managed by Panel de Control\n'
                state['profiles'][appid] = options | {'hash': hashlib.sha256(content.encode()).hexdigest(),
                                                     'launcher_hash': hashlib.sha256(launcher_content.encode()).hexdigest()}
                paused.pop(appid, None)
                state['paused'] = paused
                self._event(state, 'configure', appid)
                self._persist_files({path: content, launcher_config: launcher_content}, state)
                return {'env': {'MAKO_CONFIG': str(path), 'MAKO_PROFILE': 'pdc-' + appid,
                                'MAKO_LAUNCH_CONFIG': str(launcher_config)},
                        'wrappers': [str(self.prefix / 'bin/mako-launch')], 'profile': options}
            except (OSError, MakoError) as error:
                code = error.code if isinstance(error, MakoError) else 'mako_write_failed'
                state = self._state()
                self._event(state, 'error', appid, code)
                try:
                    self._save(state)
                except (OSError, MakoError):
                    LOG.error('MAKO action=record_error code=mako_write_failed')
                raise MakoError(code) from error

    @staticmethod
    def _process_started(pid, ticks):
        try:
            fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
            return int(fields[19]) == ticks
        except (OSError, ValueError, IndexError):
            return False

    @staticmethod
    def _namespace_pids(pid):
        try:
            for line in Path(f'/proc/{pid}/status').read_text().splitlines():
                if line.startswith('NSpid:'):
                    values = [int(value) for value in line.split()[1:]]
                    return values[1:] if values and values[0] == pid else []
        except (OSError, ValueError):
            pass
        return []

    def _process_matches(self, pid, ticks):
        if type(pid) is not int or type(ticks) is not int or pid <= 0 or ticks < 0:
            return False
        if self._process_started(pid, ticks):
            return True
        with self._lock:
            now = time.monotonic()
            if now - self._namespace_scan_at >= 2:
                candidates = {}
                try:
                    with os.scandir('/proc') as entries:
                        for index, entry in enumerate(entries):
                            if index >= 4096:
                                candidates.clear()
                                break
                            if entry.name.isdecimal():
                                host_pid = int(entry.name)
                                for namespace_pid in self._namespace_pids(host_pid):
                                    candidates.setdefault(namespace_pid, set()).add(host_pid)
                except OSError:
                    candidates.clear()
                self._namespace_candidates = candidates
                self._namespace_scan_at = now
            matches = [host_pid for host_pid in self._namespace_candidates.get(pid, ())
                       if pid in self._namespace_pids(host_pid) and self._process_started(host_pid, ticks)]
            return len(matches) == 1

    @staticmethod
    def _runtime_locked(path):
        lock = Path(str(path) + '.lock')
        try:
            descriptor = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return False
            except BlockingIOError:
                return True
            finally:
                os.close(descriptor)
        except OSError:
            return False

    def runtime(self, appid):
        appid = _appid(appid)
        empty = {'observed': False, 'active': None, 'rejections': {}}
        directory = self.config_root / appid / 'runtime-state'
        try:
            self._safe(directory)
            paths = []
            with os.scandir(directory) as entries:
                for index, entry in enumerate(entries):
                    if index >= 64:
                        break
                    if entry.name.endswith('.json') and entry.is_file(follow_symlinks=False):
                        paths.append(Path(entry.path))
        except (OSError, MakoError):
            empty['rejections']['state_unavailable'] = 1
            return empty
        states = []
        for path in paths:
            data = _json(path)
            updated = data.get('updated_unix_ms')
            reason = None
            if data.get('schema_version') != 5 or data.get('role') not in ('frame-generation', 'spatial-scaling'):
                reason = 'schema_or_role'
            elif type(updated) not in (int, float) or not 0 < updated <= (time.time() + 5) * 1000:
                reason = 'timestamp'
            elif not isinstance(data.get('requested'), dict) or data['requested'].get('name') != 'pdc-' + appid:
                reason = 'profile'
            elif not self._runtime_locked(path):
                reason = 'writer_unlocked'
            elif not self._process_matches(data.get('pid'), data.get('process_start_ticks')):
                reason = 'process_identity'
            if reason:
                empty['rejections'][reason] = empty['rejections'].get(reason, 0) + 1
                continue
            states.append(data)
        if not states:
            return empty
        data = max(states, key=lambda value: value['updated_unix_ms'])
        fields = {'multiplier', 'target_fps', 'adaptive_max_multiplier', 'flow_scale', 'performance_mode',
                  'adaptive', 'frame_generation_enabled', 'frame_generation_provisioned', 'scaling_enabled',
                  'scaling_factor', 'scaling_sharpness', 'scaling_supersampling'}
        def projection(value):
            if not isinstance(value, dict):
                return {}
            return {key: item for key, item in value.items() if key in fields and type(item) in (int, float, bool)}
        pending = data.get('pending', {})
        spatial = data.get('spatial_scaling', {})
        scaling_active = spatial.get('active') if isinstance(spatial, dict) else None
        dimensions = [spatial.get(key) for key in ('source_width', 'source_height',
                      'presentation_width', 'presentation_height')] if isinstance(spatial, dict) else []
        resolution = ({'render': dimensions[:2], 'output': dimensions[2:]}
                      if len(dimensions) == 4 and all(type(value) is int and 0 < value <= 32768
                                                     for value in dimensions) else None)
        return {'observed': True, 'rejections': empty['rejections'], 'active': data.get('frame_generation_active') if type(data.get('frame_generation_active')) is bool else None,
                'spatial_resolution': resolution,
                'role': data['role'], 'scaling_active': scaling_active if type(scaling_active) is bool else None,
                'scaling_inactive_reason': ('gamescope-presentation-target-no-headroom'
                    if isinstance(spatial, dict) and spatial.get('inactive_reason') == 'gamescope-presentation-target-no-headroom'
                    else None),
                'spatial_methods': {key: spatial[key] for key in ('requested_method', 'active_method')
                                    if isinstance(spatial, dict) and spatial.get(key) in ('native', 'mako', 'ls1', 'ls1-performance')},
                'requested': projection(data.get('requested')), 'applied': projection(data.get('applied')),
                'pending': {key: pending[key] for key in ('frame_generation_private', 'spatial_private', 'swapchain_recreation', 'process_restart')
                            if isinstance(pending, dict) and type(pending.get(key)) is bool},
                'error': 'mako_runtime_error' if data.get('error') else None}

    def report(self):
        status = self.status()
        state = self._state()
        digest = state.get('asset_sha256')
        component = {'id': 'mako-render-' + str(state.get('version', VERSION)), 'sha256': '-'.join(digest[index:index + 4] for index in range(0, 64, 4))} if isinstance(digest, str) and re.fullmatch(r'[a-f0-9]{64}', digest) else None
        return {**status, 'component': component, 'runtime': {appid: self.runtime(appid) for appid in list(status['profiles'])[:32]
                                     if re.fullmatch(r'[0-9]{1,20}', appid)},
                'events': self._report_events(state)}

    @staticmethod
    def _report_events(state):
        events = state.get('events', [])
        if not isinstance(events, list):
            return []
        return [{
            'at': event.get('at') if type(event.get('at')) is int else None,
            'action': event.get('action') if event.get('action') in ('install', 'configure', 'remove', 'error') else 'unknown',
            'appid': event.get('appid') if isinstance(event.get('appid'), str) and re.fullmatch(r'[0-9]{1,20}', event['appid']) else None,
            'code': event.get('code') if isinstance(event.get('code'), str) and re.fullmatch(r'mako_[a-z_]{1,40}', event['code']) else None,
        } for event in events[-32:] if isinstance(event, dict)]
