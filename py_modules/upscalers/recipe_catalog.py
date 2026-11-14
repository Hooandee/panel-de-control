"""Validated declarative game recipes; execution remains in the installer."""

import json
import logging
import platform as host_platform
import re
from datetime import date
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

CATALOG_PATH = Path(__file__).resolve().parents[2] / 'game-recipes'
_ID = re.compile(r'[a-z0-9][a-z0-9-]{0,79}\Z')
_HASH = re.compile(r'[a-f0-9]{64}\Z')
_ENGINES = {'optiscaler', 'dll', 'helixsr', 'proton', 'mako'}
_PLATFORMS = ('linux', 'windows')
# A block with a recipe applies on its OS; the other statuses only record that nothing applies there.
_RECIPE_STATUSES = {'tested', 'untested'}
_EMPTY_STATUSES = {'unknown', 'not_applicable'}
# Dependency kinds that only exist on one OS.
_PLATFORM_DEPENDENCIES = {'proton_dependency': 'linux', 'windows_redist': 'windows'}
_ARCHES = {'x86_64', 'aarch64'}
_VERBS = {'vcrun2022', 'msvcrt40'}
_REDISTRIBUTABLES = {'vc14_x64'}
_REDIST_PAGE_HOSTS = {'learn.microsoft.com'}
# Pages a user_files dependency may point the user to; Panel never downloads from them.
_PAGE_HOSTS = {'www.nexusmods.com', 'nexusmods.com', 'github.com', 'www.patreon.com'}
_VERSION = re.compile(r'[0-9]+(?:\.[0-9]+){0,3}\Z')
# TutorialProgress=4 marks ReShade's tutorial done: otherwise its splash stays over the game until Home is pressed.
_CONFIGURATION = {'ReShade.ini': {'Luma.SRUserType': {'2'}, 'OVERLAY.TutorialProgress': {'4'}}}


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class AssetSpec:
    id: str
    url: str
    source_url: str
    sha256: str
    size: int
    filename: str
    format: str


@dataclass(frozen=True)
class DependencySpec:
    id: str
    kind: str
    asset: str | None
    files: dict[str, str]
    provider: str | None
    verb: str | None
    requires: tuple[str, ...]
    # user_files: what the user downloads themselves where Panel can't fetch it (Nexus, Patreon).
    name: str | None = None
    page_url: str | None = None
    version: str | None = None
    avoid_versions: tuple[str, ...] = ()
    download_url: str | None = None


@dataclass(frozen=True)
class GameRecipe:
    appid: str
    name: str
    revision: int
    conditions: dict[str, tuple[str, ...]]
    exe: str
    args: tuple[str, ...]
    ini: dict[str, str]
    dependencies: tuple[str, ...]
    source_urls: tuple[str, ...]
    tested_game_builds: tuple[str, ...] = ()
    tested_at: str | None = None
    configuration: dict[str, dict[str, str]] = field(default_factory=dict)
    recommended_input: str | None = None
    effective_api: str | None = None
    quality_owner: str = "panel"
    recommended_build: str | None = None
    # Files of the selected OptiScaler build that must also sit beside the exe (PureDark's plugin looks for
    # libxess.dll there while OptiScaler 10 keeps it in its own folder).
    optiscaler_root_files: tuple[str, ...] = ()
    # REFramework's TemporalUpscaler does the upscaling (PureDark's route): Panel's quality drives its render size.
    reframework_upscaler: bool = False
    # False when OptiScaler's own frame generation breaks the game: Panel then offers only Mako or Lossless.
    optiscaler_fg: bool = True
    # Options the user must change in the game's own menu, as (setting, value) in the game's words.
    game_settings: tuple[tuple[str, str], ...] = ()
    platform: str = 'linux'
    status: str = 'tested'


@dataclass(frozen=True)
class GameEntry:
    """One game: a block per OS, each with its own recipe or only a status."""
    appid: str
    name: str
    statuses: dict[str, str]
    recipes: dict[str, GameRecipe]


@dataclass(frozen=True)
class Catalog:
    schema_version: int
    catalog_version: int
    assets: dict[str, AssetSpec]
    dependencies: dict[str, DependencySpec]
    games: dict[str, GameEntry]

    def match(self, appid: str, engine: str, platform: str | None = None, arch: str | None = None, game_build: str | None = None) -> GameRecipe | None:
        game = self.games.get(str(appid))
        platform = (platform or host_platform.system()).lower()
        entry = game.recipes.get(platform) if game else None
        if entry is None:
            return None
        if 'game_builds' in entry.conditions and game_build not in entry.conditions['game_builds']:
            return None
        arch = (arch or host_platform.machine()).lower()
        arch = {'amd64': 'x86_64', 'arm64': 'aarch64'}.get(arch, arch)
        return entry if engine in entry.conditions['engine'] and arch in entry.conditions['arch'] else None

    def dependency_order(self, ids, platform: str | None = None) -> tuple[DependencySpec, ...]:
        visited, active, ordered = set(), set(), []
        def visit(identifier):
            if identifier in active or identifier not in self.dependencies:
                raise CatalogError('dependency_cycle_or_missing')
            if identifier in visited:
                return
            active.add(identifier)
            dependency = self.dependencies[identifier]
            for child in dependency.requires:
                if platform is not None and _foreign(self.dependencies.get(child), platform):
                    continue
                visit(child)
            active.remove(identifier)
            visited.add(identifier)
            ordered.append(dependency)
        for identifier in ids:
            visit(identifier)
        return tuple(ordered)


def _object(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise CatalogError('invalid_fields')
    return value


def _text(value, limit=512):
    if not isinstance(value, str) or not value or len(value) > limit or any(ord(c) < 32 for c in value):
        raise CatalogError('invalid_text')
    return value


def _integer(value, maximum):
    if type(value) is not int or not 0 < value <= maximum:
        raise CatalogError('invalid_number')
    return value


def _game_build(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,19}', value):
        raise CatalogError('invalid_game_build')
    return value


def _identifier(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise CatalogError('invalid_id')
    return value


def _path(value):
    value = _text(value)
    parts = value.split('/')
    if value.startswith('/') or '\\' in value or ':' in value or any(p in ('', '.', '..') for p in parts):
        raise CatalogError('unsafe_path')
    if PurePosixPath(value).as_posix() != value:
        raise CatalogError('unsafe_path')
    return value


def _url(value, asset=False):
    value = _text(value, 2048)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise CatalogError('untrusted_origin') from None
    if (parsed.scheme != 'https' or parsed.hostname != 'github.com' or parsed.username or parsed.password
            or port is not None or parsed.query or parsed.fragment):
        raise CatalogError('untrusted_origin')
    if asset and not re.fullmatch(r'/[^/]+/[^/]+/releases/download/[^/]+/[^/]+', parsed.path):
        raise CatalogError('untrusted_asset_path')
    return value


def _page_url(value, hosts=_PAGE_HOSTS):
    value = _text(value, 2048)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise CatalogError('untrusted_origin') from None
    if parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or parsed.password or port is not None:
        raise CatalogError('untrusted_origin')
    return value


def _version(value):
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise CatalogError('invalid_version')
    return value


def _strings(value, validate, maximum=128):
    if not isinstance(value, list) or len(value) > maximum:
        raise CatalogError('invalid_list')
    result = tuple(validate(item) for item in value)
    if len(set(result)) != len(result):
        raise CatalogError('duplicate_value')
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError('duplicate_key')
        result[key] = value
    return result


def _read(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise CatalogError('invalid_catalog_file')
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError):
        raise CatalogError('invalid_json') from None


def _foreign(dependency: DependencySpec | None, platform: str) -> bool:
    return dependency is not None and _PLATFORM_DEPENDENCIES.get(dependency.kind, platform) != platform


def _closure(ids, dependencies, platform: str) -> list[DependencySpec]:
    # A shared dependency may require OS-specific runtimes; on another OS those edges do not apply.
    seen, pending = {}, list(ids)
    while pending:
        identifier = pending.pop()
        if identifier in seen or identifier not in dependencies:
            continue
        seen[identifier] = dependencies[identifier]
        pending.extend(child for child in seen[identifier].requires if not _foreign(dependencies.get(child), platform))
    return list(seen.values())


def _recipe(appid: str, name: str, platform: str, item, dependencies) -> GameRecipe:
    item = _object(item, ('status', 'revision', 'conditions', 'exe', 'args', 'ini', 'dependencies', 'source_urls'), ('tested_game_builds', 'tested_at', 'configuration', 'recommended_input', 'effective_api', 'quality_owner', 'recommended_build', 'optiscaler_root_files', 'reframework_upscaler', 'optiscaler_fg', 'game_settings'))
    conditions = _object(item['conditions'], ('engine', 'arch'), ('game_builds',))
    allowed = {'engine': _ENGINES, 'arch': _ARCHES}
    parsed_conditions = {}
    for key, values in conditions.items():
        if key == 'game_builds':
            builds = _strings(values, _game_build)
            if not builds:
                raise CatalogError('invalid_conditions')
            parsed_conditions[key] = builds
            continue
        values = _strings(values, _text, 8)
        if not values or not set(values) <= allowed[key]:
            raise CatalogError('invalid_conditions')
        parsed_conditions[key] = values
    args = _strings(item['args'], lambda value: _text(value, 128), 16)
    if any(not re.fullmatch(r'--?[A-Za-z0-9][A-Za-z0-9_=.-]*', value) for value in args):
        raise CatalogError('invalid_game_argument')
    settings = item['ini']
    if not isinstance(settings, dict) or len(settings) > 128:
        raise CatalogError('invalid_ini')
    for key, value in settings.items():
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_]+\.[A-Za-z0-9_]+', key):
            raise CatalogError('invalid_ini_key')
        _text(value, 256)
    ids = _strings(item['dependencies'], _identifier)
    if not set(ids) <= dependencies.keys():
        raise CatalogError('missing_dependency')
    if any(_foreign(dependencies[identifier], platform) for identifier in ids) or any(
            _foreign(dependency, platform) for dependency in _closure(ids, dependencies, platform)):
        raise CatalogError('dependency_not_for_platform')
    sources = _strings(item['source_urls'], _url, 16)
    if not sources:
        raise CatalogError('missing_source')
    configuration = item.get('configuration', {})
    if not isinstance(configuration, dict) or configuration.keys() - _CONFIGURATION.keys():
        raise CatalogError('unsupported_configuration')
    for filename, changes in configuration.items():
        _path(filename)
        if not isinstance(changes, dict) or not changes or changes.keys() - _CONFIGURATION[filename].keys():
            raise CatalogError('unsupported_configuration')
        if any(not isinstance(value, str) or value not in _CONFIGURATION[filename][key] for key, value in changes.items()):
            raise CatalogError('unsupported_configuration')
    for key, allowed in (("effective_api", ("d3d11", "d3d12", "vulkan")), ("quality_owner", ("panel", "game"))):
        if key in item and item[key] not in allowed:
            raise CatalogError("invalid_" + key)
    recommended_input = item.get('recommended_input')
    if 'recommended_input' in item and (not isinstance(recommended_input, str) or recommended_input not in ('dlss', 'fsr31', 'fsr2', 'xess')):
        raise CatalogError('invalid_recommended_input')
    recommended_build = item.get('recommended_build')
    if 'recommended_build' in item and (not isinstance(recommended_build, str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,79}', recommended_build)):
        raise CatalogError('invalid_recommended_build')
    root_files = _strings(item.get('optiscaler_root_files', []), _path, 8)
    if any('/' in name or not name.lower().endswith('.dll') for name in root_files):
        raise CatalogError('invalid_root_files')
    flags = {}
    for key, default in (('reframework_upscaler', False), ('optiscaler_fg', True)):
        flags[key] = item.get(key, default)
        if type(flags[key]) is not bool:
            raise CatalogError('invalid_' + key)
    raw_settings = item.get('game_settings', [])
    if not isinstance(raw_settings, list) or len(raw_settings) > 8:
        raise CatalogError('invalid_game_settings')
    game_settings = []
    for entry in raw_settings:
        entry = _object(entry, ('setting', 'value'))
        game_settings.append((_text(entry['setting'], 80), _text(entry['value'], 40)))
    tested_builds = _strings(item.get('tested_game_builds', []), _game_build)
    tested_at = item.get('tested_at')
    if tested_at is not None:
        try:
            if not isinstance(tested_at, str) or date.fromisoformat(tested_at).isoformat() != tested_at or not tested_builds:
                raise ValueError()
        except ValueError:
            raise CatalogError('invalid_test_date') from None
    return GameRecipe(appid, name, _integer(item['revision'], 2**31 - 1),
                      parsed_conditions, _path(item['exe']), args, dict(settings), ids, sources, tested_builds, tested_at, configuration, recommended_input, item.get("effective_api"), item.get("quality_owner", "panel"), recommended_build, root_files,
                      flags['reframework_upscaler'], flags['optiscaler_fg'], tuple(game_settings), platform, item['status'])


def load(path: Path = CATALOG_PATH) -> Catalog:
    path = Path(path)
    games_path = path / 'games'
    if path.is_symlink() or not path.is_dir() or games_path.is_symlink() or not games_path.is_dir():
        raise CatalogError('invalid_catalog_directory')
    files = [f for f in games_path.iterdir() if not f.name.startswith('.')]
    if len(files) > 512 or any(not re.fullmatch(r'[1-9][0-9]{0,9}\.json', f.name) for f in files):
        raise CatalogError('invalid_game_files')
    metadata = _object(_read(path / 'catalog.json'), ('schema_version', 'catalog_version'))
    raw = {**metadata, 'assets': _read(path / 'assets.json'),
           'dependencies': _read(path / 'dependencies.json'),
           'games': {f.stem: _read(f) for f in files}}
    raw = _object(raw, ('schema_version', 'catalog_version', 'assets', 'dependencies', 'games'))
    if type(raw['schema_version']) is not int or raw['schema_version'] != 2:
        raise CatalogError('unsupported_schema')
    version = _integer(raw['catalog_version'], 2**31 - 1)
    for key in ('assets', 'dependencies', 'games'):
        if not isinstance(raw[key], dict) or len(raw[key]) > 512:
            raise CatalogError('invalid_collection')
    assets = {}
    for identifier, item in raw['assets'].items():
        _identifier(identifier)
        item = _object(item, ('url', 'source_url', 'sha256', 'size', 'filename', 'format'))
        if not isinstance(item['sha256'], str) or not _HASH.fullmatch(item['sha256']) or item['format'] != 'zip':
            raise CatalogError('invalid_asset')
        filename = _path(item['filename'])
        if '/' in filename or not filename.endswith('.zip'):
            raise CatalogError('invalid_filename')
        assets[identifier] = AssetSpec(identifier, _url(item['url'], asset=True), _url(item['source_url']),
                                       item['sha256'], _integer(item['size'], 2 * 1024**3), filename, item['format'])
    dependencies = {}
    for identifier, item in raw['dependencies'].items():
        _identifier(identifier)
        kind = item.get('kind') if isinstance(item, dict) else None
        if kind == 'game_files':
            item = _object(item, ('kind', 'asset', 'files'), ('requires',))
            if not isinstance(item['asset'], str) or item['asset'] not in assets or not isinstance(item['files'], dict) or not 0 < len(item['files']) <= 2048:
                raise CatalogError('invalid_file_dependency')
            files = {_path(destination): _path(source) for destination, source in item['files'].items()}
            if len({name.casefold() for name in files}) != len(files):
                raise CatalogError('duplicate_destination')
            dependency = DependencySpec(identifier, kind, item['asset'], files, None, None,
                                        _strings(item.get('requires', []), _identifier))
        elif kind == 'proton_dependency':
            item = _object(item, ('kind', 'provider', 'verb'), ('requires',))
            if item['provider'] != 'winetricks' or not isinstance(item['verb'], str) or item['verb'] not in _VERBS:
                raise CatalogError('unsupported_dependency')
            dependency = DependencySpec(identifier, kind, None, {}, 'winetricks', item['verb'],
                                        _strings(item.get('requires', []), _identifier))
        elif kind == 'windows_redist':
            item = _object(item, ('kind', 'provider', 'component', 'min_version', 'page_url'), ('requires',))
            if item['provider'] != 'microsoft' or not isinstance(item['component'], str) or item['component'] not in _REDISTRIBUTABLES:
                raise CatalogError('unsupported_dependency')
            dependency = DependencySpec(identifier, kind, None, {}, 'microsoft', item['component'],
                                        _strings(item.get('requires', []), _identifier),
                                        version=_version(item['min_version']),
                                        page_url=_page_url(item['page_url'], _REDIST_PAGE_HOSTS))
        elif kind == 'user_files':
            item = _object(item, ('kind', 'name', 'page_url', 'version', 'files'), ('avoid_versions', 'requires', 'download_url'))
            if not isinstance(item['files'], dict) or not 0 < len(item['files']) <= 32:
                raise CatalogError('invalid_file_dependency')
            # The archive's layout is the author's: each file is found by its name anywhere inside it.
            files = {_path(destination): _path(member) for destination, member in item['files'].items()}
            if any('/' in member for member in files.values()) or len({n.casefold() for n in files}) != len(files):
                raise CatalogError('invalid_file_dependency')
            dependency = DependencySpec(identifier, kind, None, files, None, None,
                                        _strings(item.get('requires', []), _identifier),
                                        _text(item['name'], 80), _page_url(item['page_url']), _version(item['version']),
                                        _strings(item.get('avoid_versions', []), _version, 16),
                                        _page_url(item['download_url']) if 'download_url' in item else None)
        else:
            raise CatalogError('unsupported_dependency')
        dependencies[identifier] = dependency
    entries = {}
    for appid, item in raw['games'].items():
        if not isinstance(appid, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', appid):
            raise CatalogError('invalid_appid')
        item = _object(item, ('name', *_PLATFORMS))
        name = _text(item['name'], 160)
        statuses, recipes = {}, {}
        for platform in _PLATFORMS:
            block = item[platform]
            status = block.get('status') if isinstance(block, dict) else None
            if status in _EMPTY_STATUSES:
                _object(block, ('status',))
            elif status in _RECIPE_STATUSES:
                recipes[platform] = _recipe(appid, name, platform, block, dependencies)
            else:
                raise CatalogError('invalid_status')
            statuses[platform] = status
        entries[appid] = GameEntry(appid, name, statuses, recipes)
    catalog = Catalog(2, version, assets, dependencies, entries)
    catalog.dependency_order(dependencies)
    return catalog


@lru_cache(maxsize=1)
def bundled() -> Catalog:
    try:
        return load()
    except (OSError, CatalogError):
        logging.getLogger(__name__).warning('Game recipe catalog could not be loaded')
        return Catalog(2, 0, {}, {}, {})
