"""Where an installed game lives, which executable creates its device and what it ships."""

import json
import os
import re
import stat
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from steam_cleaner import vdf

from . import launchers, pe

STATE_FULLY_INSTALLED = 4
STATE_UPDATE_RUNNING = 256 | 1024
# Unreal keeps plugin libraries seven or eight folders down (Plugins/Nvidia/DLSS/Binaries/ThirdParty/Win64).
MAX_DEPTH = 9
MAX_PE_SCANS = 12
MANIFEST_DIR = ".pdc-upscaler"

_SKIP_EXE = re.compile(
    r"crash|unins|redist|setup|prereq|dotnet|helper|easyanticheat|battleye|eac_|"
    r"ace-(?:service|setup|base)|d3dconfig|compiler|7za|reporter|webhelper|cefprocess|vc_?redist|dxsetup|launcherpatcher|"
    # Nixxes crash reporter (crs-handler, crs-uploader, crs-video): small, imports d3d11, beats packed game exes.
    r"^crs-",
    re.I,
)
_SKIP_DIRS = {"__installer", "_commonredist", "redist", "redistributables", "directx", "support", "extras", "optiscaler"}

INPUTS = {
    "fsr31": ("amd_fidelityfx_upscaler_dx12.dll", "amd_fidelityfx_dx12.dll", "amd_fidelityfx_loader_dx12.dll"),
    "fsr2": ("ffx_fsr2_api_x64.dll", "ffx_fsr2_api_dx12_x64.dll", "ffx_fsr2_api_vk_x64.dll"),
    "dlss": ("nvngx_dlss.dll",),
    "xess": ("libxess.dll",),
    "streamline": ("sl.interposer.dll",),
    "dlssg": ("nvngx_dlssg.dll", "sl.dlss_g.dll"),
    # FSR 3.1.0-3.1.3 ship upscaler and frame generation in one amd_fidelityfx_dx12.dll.
    "fsrfg": ("amd_fidelityfx_framegeneration_dx12.dll", "amd_fidelityfx_dx12.dll"),
    "xefg": ("libxess_fg.dll",),
}
ANTI_CHEAT = ("easyanticheat", "battleye", "eac_launcher", "beservice")
FOREIGN_MARKERS = ("OptiScaler.ini", "OptiScaler.log", "FRAMEGEN_PATCH", "helixsr-install.json", "HelixSR-Scaler.files")
# What other tools leave beside the exe: OptiScaler's own files, Decky-Framegen's marker, HelixSR's records.
FOREIGN_ITEMS = (
    "OptiScaler.ini", "OptiScaler.log", "OptiScaler", "D3D12_Optiscaler", "D3D12_OptiScaler", "FRAMEGEN_PATCH",
    "helixsr-install.json", "HelixSR-Scaler.files", "helixsr.ini", "helixsr.log", "HLX_FSR.log",
)
PROXY_NAMES = ("dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "wininet.dll", "winhttp.dll", "d3d12.dll")
_SCAN_LIMIT = 96 * 1024 * 1024


@dataclass(frozen=True)
class Installed:
    appid: str
    name: str
    root: Path
    state_flags: int
    exe: str | None = None
    shortcut: bool = False
    native: bool = False
    # (launcher, game key, runner) for Heroic/Lutris shortcuts; overrides then go to the launcher.
    launcher: tuple[str, str, str | None] | None = None
    build_id: str | None = None
    # Why a shortcut is listed by Steam but has no game Panel can work on (a store game not installed).
    unavailable: str | None = None


def steam_roots(home: str) -> list[Path]:
    roots = []
    for candidate in (".local/share/Steam", ".steam/steam", ".var/app/com.valvesoftware.Steam/.local/share/Steam"):
        path = Path(home) / candidate
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved not in roots:
            roots.append(resolved)
    return roots


# Where removable drives and extra disks get mounted; a Steam library sits at most a few folders below.
MOUNT_ROOTS = ("/run/media", "/media", "/mnt")
DISCOVERY_DEPTH = 3
# Steam appids are 31-bit; a shortcut's id is a 32-bit hash, so no library can hold a manifest for it.
STEAM_APPID_LIMIT = 2**31
DISCOVERY_TTL_S = 60.0
# A share that stops answering hangs whoever lists it; discovery never walks into one.
NETWORK_FS = ("nfs", "nfs4", "cifs", "smb3", "smbfs", "9p", "davfs", "fuse.sshfs", "fuse.rclone", "afs", "ceph", "glusterfs", "autofs")
_steam_reported: dict[Path, None] = {}
_discovered: tuple[float, str, list[Path]] | None = None
_libraries_lock = threading.Lock()
_discovery_lock = threading.Lock()


def _library_path(raw: object) -> Path | None:
    if not isinstance(raw, str) or not os.path.isabs(raw) or "\0" in raw:
        return None
    return Path(os.path.normpath(raw))


def _real(path: Path) -> Path:
    try:
        return Path(os.path.realpath(path))
    except (OSError, ValueError):
        return path


def _has_steamapps(path: Path) -> bool:
    try:
        return (path / "steamapps").is_dir()
    except OSError:
        return False


def set_steam_libraries(paths) -> None:
    """The mounted library folders Steam itself lists (InstallFolder store), replacing the last list."""
    folders = [path for path in (_library_path(raw) for raw in list(paths or ())[:32]) if path is not None]
    with _libraries_lock:
        _steam_reported.clear()
        _steam_reported.update(dict.fromkeys(folders))


def _lenient_index(raw: bytes) -> list[str]:
    """Paths from an index the strict reader refused (repeated keys, stray bytes): Steam itself still loads it."""
    text = raw[:vdf.MAX_BYTES].decode("utf-8", errors="replace")
    found = re.findall(r'"path"\s+"((?:\\.|[^"\\])*)"', text, re.I)
    found += re.findall(r'"\d+"\s+"(/(?:\\.|[^"\\])*)"', text)
    return [re.sub(r'\\([\\"])', r"\1", value) for value in found]


def _network_mounts(mountinfo: str = "/proc/self/mountinfo") -> set[str]:
    mounts = set()
    try:
        with open(mountinfo, encoding="utf-8", errors="replace") as source:
            for line in source:
                fields, _sep, rest = line.partition(" - ")
                parts, kind = fields.split(), rest.split()[:1]
                if len(parts) > 4 and kind and kind[0] in NETWORK_FS:
                    mounts.add(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), parts[4]))
    except OSError:
        pass
    return mounts


def _discover(home: str) -> list[Path]:
    """Steam libraries on local mounted drives and in the home folder, found by looking: the last resort."""
    global _discovered
    with _discovery_lock:
        now = time.monotonic()
        if _discovered and _discovered[1] == home and now - _discovered[0] < DISCOVERY_TTL_S:
            return list(_discovered[2])
        network = _network_mounts()
        found: list[Path] = []
        for base in (*MOUNT_ROOTS, home):
            pending = [(_real(Path(base)), 0)]
            while pending:
                folder, depth = pending.pop()
                if str(folder) in network:
                    continue
                try:
                    with os.scandir(folder) as entries:
                        children = [Path(e.path) for e in entries if e.is_dir(follow_symlinks=False) and not e.name.startswith(".")]
                except OSError:
                    continue
                for child in children:
                    if child.name == "steamapps":
                        real = _real(folder)
                        if real not in found:
                            found.append(real)
                    elif depth + 1 < DISCOVERY_DEPTH and child.name not in ("compatdata", "shadercache", "common"):
                        pending.append((child, depth + 1))
        _discovered = (now, home, found)
        return list(found)


def _library_candidates(home: str, counts: Counter, live_folders: tuple[str, ...] | None) -> Iterator[tuple[Path, str]]:
    for root in steam_roots(home):
        yield root, "root"
        index = root / "steamapps/libraryfolders.vdf"
        try:
            raw = _regular_bytes(index, vdf.MAX_BYTES)
            if len(raw) > vdf.MAX_BYTES:
                raise ValueError("oversized_vdf")
            folders = vdf.parse_text(raw).get("libraryfolders")
            if not isinstance(folders, dict):
                raise ValueError("malformed_vdf")
        except FileNotFoundError:
            counts["missing_index"] += 1
            folders = {}
        except OSError:
            counts["unreadable_index"] += 1
            folders = {}
        except ValueError:
            counts["invalid_index"] += 1
            folders = {}
            lenient = _lenient_index(raw)
            counts["lenient_path"] += len(lenient)
            for candidate in lenient:
                path = _library_path(candidate)
                if path is not None:
                    yield path, "lenient_index"
        else:
            counts["read_index"] += 1
        for key, entry in folders.items():
            if not key.isdecimal():
                continue
            path = _library_path(entry.get("path") if isinstance(entry, dict) else entry)
            if path is None:
                counts["invalid_entry"] += 1
                continue
            counts["path_object" if isinstance(entry, dict) else "direct_path"] += 1
            yield path, "index"
    if live_folders is None:
        with _libraries_lock:
            reported = list(_steam_reported)
    else:
        reported = [path for raw in live_folders if (path := _library_path(raw)) is not None]
    for path in reported:
        yield path, "steam"


def _available_libraries(home: str, counts: Counter, live_folders: tuple[str, ...] | None = None) -> Iterator[tuple[Path, str]]:
    seen = set()
    for path, source in _library_candidates(home, counts, live_folders):
        real = _real(path)
        if real in seen:
            continue
        if source == "steam":
            counts["steam_unindexed"] += 1
        if _has_steamapps(real):
            seen.add(real)
            yield real, source
        else:
            counts["unavailable_library"] += 1
    counts["available"] = len(seen)


def library_paths(home: str, counts: Counter | None = None) -> list[Path]:
    return [path for path, _ in _available_libraries(home, Counter() if counts is None else counts)]


def library_summary(home: str) -> dict:
    counts = Counter()
    sources = dict(_available_libraries(home, counts))
    return {**counts, "sources": dict(Counter(sources.values()))}


def update_state(flags: int) -> str | None:
    """None when Steam has nothing pending, else `running` (downloading) or `pending`."""
    if flags == STATE_FULLY_INSTALLED:
        return None
    return "running" if flags & STATE_UPDATE_RUNNING else "pending"


def _unquote(value: object) -> str:
    return str(value or "").strip().strip('"')


def from_launcher(home: str, appid: str, exe: str, launch_options: str) -> Installed | None:
    found = launchers.identify(exe, launch_options)
    if not found:
        return None
    game = launchers.find(home, *found)
    if game is None:
        return None
    return Installed(appid, game.name, game.root, STATE_FULLY_INSTALLED, game.exe, True, game.native, found)


def _wrapped(home: str, appid: str, name: str, exe: str, launch_options: str) -> Installed | None:
    """A shortcut to a script (PortProton, Unifideck, a hand-written wrapper) that runs a Windows game."""
    target = launchers.wrapped_exe(home, exe, launch_options)
    if target is None:
        return None
    root = launchers.game_root(target)
    return Installed(appid, name, root, STATE_FULLY_INSTALLED, target.relative_to(root).as_posix(), True)


def _script_shortcut(home: str, appid: str, name: str, exe: str, launch_options: str, start: Path) -> Installed:
    """A shortcut that does not point at a .exe: a script running a Windows game, or something native."""
    wrapped = _wrapped(home, appid, name, exe, launch_options) if home else None
    if wrapped:
        return wrapped
    key = launchers.unifideck_key(launch_options) if home and "unifideck" in exe.lower() else None
    if key:
        row = launchers.unifideck_row(home, key)
        if row is None or not row[0]:
            return Installed(appid, name, start, STATE_FULLY_INSTALLED, None, True, native=True,
                             unavailable="unifideck_not_installed" if row is None else "unifideck_no_exe")
        if not Path(row[0]).is_file():
            return Installed(appid, name, start, STATE_FULLY_INSTALLED, None, True, native=True,
                             unavailable="unifideck_missing")
    # Otherwise an AppImage, script or Linux binary: its start folder is not a Windows game to patch.
    return Installed(appid, name, start, STATE_FULLY_INSTALLED, None, True, native=True)


def find_shortcut(home: str, appid: str) -> Installed | None:
    """A non-Steam shortcut: any executable added to Steam, wherever it came from."""
    for root in steam_roots(home):
        try:
            profiles = [p for p in (root / "userdata").iterdir() if p.name.isdecimal()]
        except OSError:
            continue
        for profile in profiles:
            try:
                shortcuts = vdf.read_shortcuts(profile / "config/shortcuts.vdf")
            except (OSError, ValueError, UnicodeError):
                continue
            for entry in shortcuts.values() if isinstance(shortcuts, dict) else ():
                if not isinstance(entry, dict) or str(entry.get("appid")) != appid:
                    continue
                launched = from_launcher(home, appid, _unquote(entry.get("exe")), str(entry.get("launchoptions") or ""))
                if launched:
                    return launched
                exe = Path(_unquote(entry.get("exe")))
                start = Path(_unquote(entry.get("startdir"))) if _unquote(entry.get("startdir")) else exe.parent
                if not start.is_dir():
                    return None
                name = str(entry.get("appname") or appid)
                if exe.suffix.lower() != ".exe":
                    return _script_shortcut(home, appid, name, str(exe), str(entry.get("launchoptions") or ""), start)
                relative = None
                if exe.is_file():
                    try:
                        relative = exe.resolve().relative_to(start.resolve()).as_posix()
                    except ValueError:
                        start, relative = exe.parent, exe.name
                return Installed(appid, name, start, STATE_FULLY_INSTALLED, relative, True)
    return None


def from_hint(appid: str, hint: dict | None, home: str = "") -> Installed | None:
    """A shortcut described by Steam's own app details, for when shortcuts.vdf does not list it."""
    if not isinstance(hint, dict):
        return None
    if home:
        launched = from_launcher(home, appid, _unquote(hint.get("exe")), str(hint.get("opts") or ""))
        if launched:
            return launched
    exe = Path(_unquote(hint.get("exe")))
    start = Path(_unquote(hint.get("dir"))) if _unquote(hint.get("dir")) else exe.parent
    if not str(exe) or not start.is_dir():
        return None
    name = str(hint.get("name") or appid)
    if exe.suffix.lower() != ".exe":
        return _script_shortcut(home, appid, name, str(exe), str(hint.get("opts") or ""), start)
    try:
        relative = exe.resolve().relative_to(start.resolve()).as_posix()
    except (ValueError, OSError):
        start, relative = exe.parent, exe.name
    return Installed(appid, name, start, STATE_FULLY_INSTALLED, relative, True)


_linux_builds: dict[str, tuple[tuple, bool]] = {}


def _is_elf(path: Path) -> bool:
    try:
        if ".so" in path.suffixes or not os.access(path, os.X_OK):
            return False
        with path.open("rb") as stream:
            return stream.read(4) == b"\x7fELF"
    except OSError:
        return False


def linux_build(root: Path, build_id: str | None = None) -> bool:
    """Steam installed the game's own Linux build: a Linux binary near the top and not one .exe anywhere.

    The shallow look for the binary comes first, so Windows games never pay for the walk that rules out every .exe;
    the answer is remembered per folder until Steam changes it."""
    try:
        stamp = (build_id, root.stat().st_mtime_ns)
    except OSError:
        return False
    cached = _linux_builds.get(str(root))
    if cached and cached[0] == stamp:
        return cached[1]
    depth = len(root.parts)
    binary = False
    for current, dirs, files in os.walk(root):
        if len(Path(current).parts) - depth >= 2:
            dirs[:] = []
        if any(_is_elf(Path(current) / name) for name in files):
            binary = True
            break
    result = binary and not any(name.lower().endswith(".exe") for _current, _dirs, files in os.walk(root) for name in files)
    _linux_builds[str(root)] = (stamp, result)
    return result


def _lenient_manifest(manifest: Path) -> dict:
    """The few top-level fields Panel needs from a manifest the strict reader refused; Steam still loads it."""
    with open(manifest, "rb") as source:
        text = source.read(vdf.MAX_BYTES).decode("utf-8", errors="replace")
    opening = text.find("{")
    nested = text.find("{", opening + 1)
    top = text[opening + 1:nested if nested > opening else len(text)]
    state = {}
    for key in ("appid", "name", "installdir", "stateflags", "buildid"):
        match = re.search(rf'"{key}"\s+"((?:\\.|[^"\\])*)"', top, re.I)
        if match:
            state[key] = re.sub(r'\\([\\"])', r"\1", match.group(1))
    return state


def _install_root(apps: Path, state: dict) -> Path | None:
    installdir = state.get("installdir")
    if not isinstance(installdir, str) or installdir in ("", ".", "..") or "/" in installdir or "\0" in installdir:
        return None
    return apps / "common" / installdir


def _regular_bytes(path: str | Path, limit: int, *, nofollow: bool = False) -> bytes:
    flags = os.O_NONBLOCK | (os.O_NOFOLLOW if nofollow else 0)
    with open(path, "rb", opener=lambda name, mode: os.open(name, mode | flags)) as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise OSError("not_regular")
        return source.read(limit + 1)


def _selector_manifest(path: str, appid: str) -> str | None:
    """None when the manifest proves an installed game, else why it does not."""
    limit = 128 * 1024
    raw = _regular_bytes(path, limit, nofollow=True)
    if len(raw) > limit:
        raise ValueError("oversized_manifest")
    state = vdf.parse_text(raw).get("appstate")
    if not isinstance(state, dict) or state.get("appid") != appid:
        raise ValueError("invalid_appid")
    try:
        flags = int(state.get("stateflags", ""))
    except ValueError:
        return "invalid"
    # An installed game keeps this bit while Steam updates, validates or queues it.
    if not flags & STATE_FULLY_INSTALLED:
        return "not_installed"
    root = _install_root(Path(path).parent, state)
    return None if root is not None and root.is_dir() else "no_folder"


def selector_installs(home: str, live_folders: tuple[str, ...] = (), on_confirmed: Callable[[int], None] | None = None) -> dict:
    """Positive evidence only. A partial inventory can still recover games from reachable libraries."""
    appids: set[int] = set()
    counts = Counter()
    rejected = Counter()
    deadline = time.monotonic() + 3.0
    complete = True
    remaining = 1024

    def result(done: bool) -> dict:
        return {"appids": sorted(appids), "complete": done, "rejected": dict(rejected)}

    for library, _ in _available_libraries(home, counts, live_folders):
        try:
            with os.scandir(library / "steamapps") as entries:
                for entry in entries:
                    if remaining == 0 or time.monotonic() >= deadline:
                        return result(False)
                    match = re.fullmatch(r"appmanifest_([1-9][0-9]{0,9})\.acf", entry.name)
                    if not match or int(match[1]) >= STEAM_APPID_LIMIT:
                        continue
                    remaining -= 1
                    try:
                        reason = _selector_manifest(entry.path, match[1])
                    except (OSError, ValueError):
                        rejected["unreadable"] += 1
                        complete = False
                        continue
                    if reason is not None:
                        rejected[reason] += 1
                        continue
                    appid = int(match[1])
                    if appid not in appids:
                        appids.add(appid)
                        if on_confirmed is not None:
                            on_confirmed(appid)
        except OSError:
            complete = False
    errors = ("unavailable_library", "unreadable_index", "invalid_index", "invalid_entry", "missing_index")
    return result(complete and bool(counts["available"]) and not any(counts[key] for key in errors))


def _manifest_game(library: Path, appid: str, contained: bool = False) -> tuple[str, Installed | None]:
    apps = library / "steamapps"
    manifest = apps / f"appmanifest_{appid}.acf"
    try:
        state = vdf.read_text(manifest).get("appstate")
    except FileNotFoundError:
        return "manifest_missing", None
    except OSError:
        return "manifest_unreadable", None
    except ValueError:
        try:
            state = _lenient_manifest(manifest)
        except OSError:
            return "manifest_unreadable", None
    if not isinstance(state, dict) or state.get("appid", appid) != appid:
        return "manifest_invalid", None
    root = _install_root(apps, state)
    if root is None:
        return "manifest_invalid", None
    if contained and (root.is_symlink() or not _real(root).is_relative_to(_real(apps / "common"))):
        return "folder_outside", None
    try:
        if not stat.S_ISDIR(root.stat().st_mode):
            return "folder_missing", None
    except (FileNotFoundError, NotADirectoryError):
        return "folder_missing", None
    except OSError:
        return "folder_unreadable", None
    try:
        flags = int(state.get("stateflags", 0))
    except (TypeError, ValueError):
        flags = 0
    build_id = str(state["buildid"]) if str(state.get("buildid", "")).isdecimal() else None
    return "found", Installed(appid, str(state.get("name") or appid), root, flags,
                              native=linux_build(root, build_id), build_id=build_id)


def find_installed(home: str, appid: str, lookup: Counter | None = None) -> Installed | None:
    """The game in a library Steam vouches for; only when none of them even has its manifest, a library found
    on a mounted drive, so a stale copy never wins over the install Steam knows."""
    if not appid.isdecimal():
        return None
    if len(appid) > 10 or int(appid) >= STEAM_APPID_LIMIT:
        return find_shortcut(home, appid)
    counts = Counter() if lookup is None else lookup
    trusted = dict(_available_libraries(home, counts))
    known = False
    for library, source in trusted.items():
        outcome, installed = _manifest_game(library, appid)
        counts[outcome] += 1
        known = known or outcome != "manifest_missing"
        if installed is not None:
            counts[f"found_{source}"] += 1
            return installed
    if not known:
        for library in _discover(home):
            if library in trusted:
                continue
            counts["discovered"] += 1
            outcome, installed = _manifest_game(library, appid, contained=True)
            if outcome != "manifest_missing":
                counts[f"discovery_{outcome}"] += 1
            if installed is not None:
                counts["found_discovery"] += 1
                return installed
    return find_shortcut(home, appid)


def _walk(root: Path):
    root_depth = len(root.parts)
    for current, dirs, files in os.walk(root):
        depth = len(Path(current).parts) - root_depth
        dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith(".")] if depth < MAX_DEPTH else []
        yield Path(current), files


def _installed_by_panel(folder: Path) -> set[str]:
    """Lower-case names Panel put in `folder`; replaced game files stay the game's."""
    try:
        manifest = json.loads((folder / MANIFEST_DIR / "manifest.json").read_text())
    except (OSError, ValueError):
        return set()
    backups = set(manifest.get("backups", []))
    return {Path(name).name.lower() for name in manifest.get("files", {}) if name not in backups and "/" not in name}


_SL_VERSION = re.compile(r"(?:^|v)(\d+)[.,]\d+")


def streamline_major(path: Path) -> int | None:
    """NVIDIA leaves FileVersion out of some builds; OriginalFilename then carries "v2.14.1"."""
    strings = pe.version_strings(str(path))
    for key in ("FileVersion", "ProductVersion", "OriginalFilename"):
        match = _SL_VERSION.search(strings.get(key, ""))
        if match:
            return int(match.group(1))
    return None


def _score(path: Path, root: Path, size: int) -> int:
    name = path.name.lower()
    relative = path.relative_to(root).as_posix().lower()
    score = 0
    if name.endswith("-win64-shipping.exe"):
        score += 50
    if "binaries/win64" in relative:
        score += 20
    if relative.startswith("engine/"):
        score -= 40
    if "launcher" in name:
        score -= 25
    if (path.parent / f"{path.stem}_Data").is_dir():
        score += 40
    score += min(size // (8 * 1024 * 1024), 20)
    return score


SHIPPED_NAMES = {"dlss": "DLSS", "fsr31": "FSR 3.1", "fsr2": "FSR 2", "xess": "XeSS"}


def shipped_upscalers(root: Path) -> list[str]:
    """The DLSS, FSR and XeSS libraries the game folder carries, by name, in a fixed order."""
    found = set()
    largest: tuple[int, Path] | None = None
    for current, files in _walk(root):
        ours = _installed_by_panel(current)
        for file in files:
            lower = file.lower()
            for kind in SHIPPED_NAMES:
                if lower in INPUTS[kind] and lower not in ours:
                    found.add(kind)
            if lower.endswith(".exe") and not _SKIP_EXE.search(lower):
                try:
                    size = (current / file).stat().st_size
                except OSError:
                    continue
                if largest is None or size > largest[0]:
                    largest = (size, current / file)
    if largest and not found:
        found |= embedded_upscalers(largest[1])
    return [SHIPPED_NAMES[kind] for kind in SHIPPED_NAMES if kind in found]


def _graphics_apis(exe: Path) -> list[str]:
    """The exe's graphics imports. RE Engine games import only d3d11/dxgi and load D3D12 at runtime; the Agility SDK
    beside their exe is what gives the D3D12 device away. Other games keep what they import."""
    apis = set(pe.graphics_apis(str(exe)))
    if (exe.parent / "D3D12" / "D3D12Core.dll").is_file() and any(exe.parent.glob("re_chunk_000.pak*")):
        apis = (apis - {"d3d11"}) | {"d3d12"}
    return sorted(apis)


def _creates_device(apis: list[str]) -> bool:
    return any(api in apis for api in ("d3d12", "d3d11", "vulkan"))


def analyze(root: Path, chosen_exe: str | None = None, recipe_exe: str | None = None) -> dict:
    """Candidates for the device-creating executable plus what the game ships.

    `chosen_exe` (relative to `root`) wins when it still exists: the user picked it.
    Otherwise a recipe's known executable beats the heuristic.
    """
    exes: list[tuple[int, Path, int]] = []
    inputs: dict[str, list[str]] = {key: [] for key in INPUTS}
    dll_targets: list[str] = []
    anti_cheat = False
    for current, files in _walk(root):
        ours = _installed_by_panel(current)
        lower_dir = current.as_posix().lower()
        if any(marker in lower_dir for marker in ANTI_CHEAT):
            anti_cheat = True
        for file in files:
            lower = file.lower()
            path = current / file
            # Combined libraries need a loader plus effect providers, checked against the chosen build.
            if lower in {"amd_fidelityfx_upscaler_dx12.dll", "amd_fidelityfx_loader_dx12.dll", "amd_fidelityfx_dx12.dll"} and lower not in ours and path.is_file() and not path.is_symlink():
                dll_targets.append(path.relative_to(root).as_posix())
            if any(marker in lower for marker in ANTI_CHEAT):
                anti_cheat = True
            for kind, names in INPUTS.items():
                if lower in names and lower not in ours:
                    inputs[kind].append((current / file).relative_to(root).as_posix())
            if lower.endswith(".exe") and not _SKIP_EXE.search(lower):
                path = current / file
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                exes.append((_score(path, root, size), path, size))

    exes.sort(key=lambda item: (-item[0], -item[2], item[1].as_posix()))
    candidates = []
    for index, (score, path, size) in enumerate(exes[:MAX_PE_SCANS]):
        apis = _graphics_apis(path)
        if _creates_device(apis):
            score += 30
        candidates.append({
            "exe": path.relative_to(root).as_posix(),
            "apis": apis,
            "size": size,
            "score": score,
        })
    # On a tie the exe that imports a graphics API wins: Unity extras (a guide, an artbook) score
    # as much as the game through their _Data folder.
    candidates.sort(key=lambda item: (-item["score"], not _creates_device(item["apis"]), item["exe"]))

    manual = False
    selected = candidates[0] if candidates else None
    if not chosen_exe and recipe_exe and (root / recipe_exe).is_file():
        selected = next((c for c in candidates if c["exe"] == recipe_exe), None) or {
            "exe": recipe_exe, "apis": _graphics_apis(root / recipe_exe),
            "size": (root / recipe_exe).stat().st_size, "score": 0,
        }
    if chosen_exe and (root / chosen_exe).is_file():
        manual = True
        selected = next((c for c in candidates if c["exe"] == chosen_exe), None) or {
            "exe": chosen_exe,
            "apis": _graphics_apis(root / chosen_exe),
            "size": (root / chosen_exe).stat().st_size,
            "score": 0,
        }

    target = (root / selected["exe"]).parent if selected else None
    if selected:
        for kind in embedded_upscalers(root / selected["exe"]):
            if not inputs[kind]:
                inputs[kind].append(selected["exe"])
    foreign = bool(target) and not (target / MANIFEST_DIR).exists() and any(
        (target / marker).exists() for marker in FOREIGN_MARKERS
    )
    return {
        "candidates": candidates[:6],
        "exe": selected["exe"] if selected else None,
        "apis": selected["apis"] if selected else [],
        "manual": manual,
        "target": str(target) if target else None,
        "inputs": {kind: sorted(paths)[:4] for kind, paths in inputs.items() if paths},
        "dll_targets": sorted(dll_targets),
        "streamline": streamline_major(root / sorted(inputs["streamline"])[0]) if inputs["streamline"] else None,
        "anti_cheat": anti_cheat,
        "foreign": foreign,
        "foreign_identity": foreign_identity(target) if foreign else None,
    }


def running_under(root: Path, proc: str = "/proc") -> bool:
    """Whether any process command line points inside the game folder."""
    unix = root.as_posix().lower()
    wine = ("z:" + unix).replace("/", "\\")
    try:
        entries = os.listdir(proc)
    except OSError:
        return False
    for pid in entries:
        if not pid.isdecimal():
            continue
        try:
            with open(os.path.join(proc, pid, "cmdline"), "rb") as handle:
                cmdline = handle.read(8192).decode("utf-8", "replace").lower()
        except OSError:
            continue
        if unix in cmdline or wine in cmdline:
            return True
    return False


# Upscalers compiled into the game's own executable leave their entry points as strings.
EMBEDDED = {"fsr2": (b"ffxFsr2ContextCreate",), "fsr31": (b"ffxFsr3UpscalerContextCreate",), "xess": (b"xessD3D12CreateContext",)}


# A cached exe scans at full speed and each `in` holds the GIL: every sysfs read the event loop makes
# then waits behind it. Small chunks and a short pause every few keep the loop answering.
_EMBEDDED_CHUNK = 256 * 1024
_EMBEDDED_PAUSE_EVERY = 4
_EMBEDDED_PAUSE_S = 0.001
_EMBEDDED_OVERLAP = max(len(n) for needles in EMBEDDED.values() for n in needles) - 1
_embedded_cache: dict[str, tuple[tuple[int, int], frozenset[str]]] = {}
_embedded_lock = threading.Lock()


def embedded_upscalers(exe: Path) -> set[str]:
    # Plain reads, not mmap: mmap.find holds the GIL while it pages the exe in from a slow SD card.
    try:
        info = os.stat(exe)
    except OSError:
        return set()
    key, stamp = str(exe), (info.st_size, info.st_mtime_ns)
    with _embedded_lock:
        cached = _embedded_cache.get(key)
    if cached and cached[0] == stamp:
        return set(cached[1])
    pending = dict(EMBEDDED)
    found: set[str] = set()
    try:
        with open(exe, "rb") as handle:
            tail = b""
            chunks = 0
            while pending:
                chunk = handle.read(_EMBEDDED_CHUNK)
                if not chunk:
                    break
                window = tail + chunk
                for kind in [k for k, needles in pending.items() if any(n in window for n in needles)]:
                    found.add(kind)
                    del pending[kind]
                tail = window[-_EMBEDDED_OVERLAP:]
                chunks += 1
                if chunks % _EMBEDDED_PAUSE_EVERY == 0:
                    time.sleep(_EMBEDDED_PAUSE_S)
    except OSError:
        return set()
    with _embedded_lock:
        if len(_embedded_cache) >= 512:
            _embedded_cache.clear()
        _embedded_cache[key] = (stamp, frozenset(found))
    return found


def is_optiscaler(path: Path) -> bool:
    """A proxy DLL is someone's OptiScaler only if its own strings say so; a game's real dxgi.dll never does."""
    try:
        with open(path, "rb") as handle:
            tail = b""
            read = 0
            while read < _SCAN_LIMIT:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    return False
                if b"OptiScaler" in tail + chunk:
                    return True
                tail = chunk[-16:]
                read += len(chunk)
    except OSError:
        return False
    return False



_FOREIGN_READ_LIMIT = 256 * 1024


def _foreign_text(target: Path, name: str) -> str | None:
    path = target / name
    try:
        if target.is_symlink() or any((target / parent).is_symlink() for parent in Path(name).parents):
            return None
        if path.is_symlink() or not path.is_file():
            return None
        with path.open("rb") as handle:
            data = handle.read(_FOREIGN_READ_LIMIT + 1)
        if len(data) > _FOREIGN_READ_LIMIT:
            return None
        return data.decode("utf-8")
    except (OSError, UnicodeError):
        return None


def _scaler_manifest(target: Path) -> tuple[str | None, bool]:
    text = _foreign_text(target, "HelixSR-Scaler.files")
    if text is None or len(text.splitlines()) > 512:
        return None, True
    lines = text.splitlines()
    if not lines or lines[0].strip() != "# HelixSR Scaler, installed by HelixSR Desktop":
        return None, True
    layouts = [line.removeprefix("# layout=").strip() for line in lines if line.startswith("# layout=")]
    names = [line.removeprefix("name=").strip() for line in lines if line.startswith("name=")]
    files = [line.strip() for line in lines if line.strip() and not line.startswith(("#", "name="))]
    if len(layouts) != 1 or len(names) != 1 or names[0] not in PROXY_NAMES or len(files) != len(set(files)):
        return None, True
    for name in files:
        path = Path(name)
        if (path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or "\x00" in name
                or name != path.as_posix() or any((target / part).is_symlink() for part in (path, *path.parents))):
            return None, True
    if layouts[0] != "ngx":
        return None, True
    required = (names[0], "OptiScaler.ini", "HelixSR/helixsr.dll")
    if not all(name in files and (target / name).is_file() for name in required):
        return None, True
    config = _foreign_text(target, "OptiScaler.ini")
    if config is None or "HelixSR Scaler" not in config or "[HelixSR]" not in config:
        return None, True
    try:
        for name in (names[0], "HelixSR/helixsr.dll"):
            fd = os.open(target / name, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as handle:
                if handle.read(2) != b"MZ":
                    return None, True
    except OSError:
        return None, True
    return "dlss", False


def foreign_identity(target: Path) -> dict:
    evidence: list[str] = []
    variants: set[str] = set()
    manifest_error = False
    marker = target / "helixsr-install.json"
    helix = marker.exists() or marker.is_symlink()
    if helix:
        evidence.append("helixsr-install.json")
        try:
            record = json.loads(_foreign_text(target, "helixsr-install.json") or "")
            manifest_error = not isinstance(record, dict)
            if isinstance(record, dict) and "files" in record:
                manifest_error = not isinstance(record["files"], list) or any(
                    not isinstance(name, str) for name in record["files"]
                )
        except (ValueError, RecursionError):
            manifest_error = True
    scaler_marker = target / "HelixSR-Scaler.files"
    if scaler_marker.exists() or scaler_marker.is_symlink():
        helix = True
        evidence.append("HelixSR-Scaler.files")
        variant, invalid = _scaler_manifest(target)
        manifest_error = manifest_error or invalid
        if variant:
            variants.add(variant)
    for name in ("OptiScaler.log", "helixsr.log", "HLX_FSR.log", "HelixSR-fsrfg/helixsr.log", "_storage_/HLX_FSR.log"):
        content = _foreign_text(target, name)
        if content is None:
            continue
        if re.search(r"FFX upscaler:\s*HLX DLSS\b", content):
            helix = True
            variants.add("dlss")
            evidence.append(f"{name}:HLX DLSS")
        if "HLX-FSR-4 own runtime active:" in content:
            helix = True
            variants.add("fsr")
            evidence.append(f"{name}:HLX FSR 4")
    if helix:
        return {"engine": "helixsr", "variant": next(iter(variants)) if len(variants) == 1 and not manifest_error else "unknown",
                "evidence": evidence, "manifest_error": manifest_error}
    for name in ("OptiScaler.ini", "OptiScaler.log"):
        if _foreign_text(target, name) is not None:
            evidence.append(name)
    return {"engine": "optiscaler" if evidence else "unknown", "variant": "unknown",
            "evidence": evidence, "manifest_error": False}


def foreign_items(target: Path) -> list[str]:
    items = [name for name in FOREIGN_ITEMS if (target / name).exists()]
    return items + [name for name in PROXY_NAMES if (target / name).is_file() and is_optiscaler(target / name)]


def helix_swaps(target: Path) -> list[str]:
    """Game DLLs HelixSR replaced: their originals wait beside them as *.original.dll."""
    try:
        record = json.loads((target / "helixsr-install.json").read_text())
    except (OSError, ValueError):
        return []
    names = record.get("files") if isinstance(record, dict) else None
    return [n for n in names or [] if isinstance(n, str) and "/" not in n and (target / Path(n).with_suffix(".original.dll").name).is_file()]
