"""Where an installed game lives, which executable creates its device and what it ships."""

import json
import mmap
import os
import re
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
    r"d3dconfig|compiler|7za|reporter|webhelper|cefprocess|vc_?redist|dxsetup|launcherpatcher",
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
FOREIGN_MARKERS = ("OptiScaler.ini", "OptiScaler.log", "FRAMEGEN_PATCH", "helixsr-install.json")
# What other tools leave beside the exe: OptiScaler's own files, Decky-Framegen's marker, HelixSR's records.
FOREIGN_ITEMS = (
    "OptiScaler.ini", "OptiScaler.log", "OptiScaler", "D3D12_Optiscaler", "D3D12_OptiScaler", "FRAMEGEN_PATCH",
    "helixsr-install.json", "helixsr.ini", "helixsr.log", "HLX_FSR.log",
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


def steam_roots(home: str) -> list[Path]:
    roots = []
    for candidate in (".local/share/Steam", ".steam/steam", ".var/app/com.valvesoftware.Steam/.local/share/Steam"):
        path = Path(home) / candidate
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        if resolved not in roots:
            roots.append(resolved)
    return roots


def library_paths(home: str) -> list[Path]:
    libraries: list[Path] = []
    for root in steam_roots(home):
        candidates = [root]
        try:
            folders = vdf.read_text(root / "steamapps/libraryfolders.vdf").get("libraryfolders") or {}
        except (OSError, ValueError):
            folders = {}
        for entry in folders.values() if isinstance(folders, dict) else ():
            if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                candidates.append(Path(entry["path"]))
        for path in candidates:
            if (path / "steamapps").is_dir() and path not in libraries:
                libraries.append(path)
    return libraries


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
                    # An AppImage, script or Linux binary: its start folder is not a Windows game to patch.
                    return Installed(appid, name, start, STATE_FULLY_INSTALLED, None, True, native=True)
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
        return Installed(appid, name, start, STATE_FULLY_INSTALLED, None, True, native=True)
    try:
        relative = exe.resolve().relative_to(start.resolve()).as_posix()
    except (ValueError, OSError):
        start, relative = exe.parent, exe.name
    return Installed(appid, name, start, STATE_FULLY_INSTALLED, relative, True)


def find_installed(home: str, appid: str) -> Installed | None:
    if not appid.isdecimal():
        return None
    for library in library_paths(home):
        manifest = library / "steamapps" / f"appmanifest_{appid}.acf"
        try:
            state = vdf.read_text(manifest).get("appstate") or {}
        except (OSError, ValueError):
            continue
        installdir = state.get("installdir")
        if not isinstance(installdir, str) or not installdir or "/" in installdir:
            continue
        root = library / "steamapps" / "common" / installdir
        if root.is_dir():
            try:
                flags = int(state.get("stateflags", 0))
            except (TypeError, ValueError):
                flags = 0
            return Installed(appid, str(state.get("name") or appid), root, flags)
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


def analyze(root: Path, chosen_exe: str | None = None, recipe_exe: str | None = None) -> dict:
    """Candidates for the device-creating executable plus what the game ships.

    `chosen_exe` (relative to `root`) wins when it still exists: the user picked it.
    Otherwise a recipe's known executable beats the heuristic.
    """
    exes: list[tuple[int, Path, int]] = []
    inputs: dict[str, list[str]] = {key: [] for key in INPUTS}
    anti_cheat = False
    for current, files in _walk(root):
        ours = _installed_by_panel(current)
        lower_dir = current.as_posix().lower()
        if any(marker in lower_dir for marker in ANTI_CHEAT):
            anti_cheat = True
        for file in files:
            lower = file.lower()
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
        apis = pe.graphics_apis(str(path))
        if any(api in apis for api in ("d3d12", "d3d11", "vulkan")):
            score += 30
        candidates.append({
            "exe": path.relative_to(root).as_posix(),
            "apis": apis,
            "size": size,
            "score": score,
        })
    candidates.sort(key=lambda item: (-item["score"], item["exe"]))

    manual = False
    selected = candidates[0] if candidates else None
    if not chosen_exe and recipe_exe and (root / recipe_exe).is_file():
        selected = next((c for c in candidates if c["exe"] == recipe_exe), None) or {
            "exe": recipe_exe, "apis": pe.graphics_apis(str(root / recipe_exe)),
            "size": (root / recipe_exe).stat().st_size, "score": 0,
        }
    if chosen_exe and (root / chosen_exe).is_file():
        manual = True
        selected = next((c for c in candidates if c["exe"] == chosen_exe), None) or {
            "exe": chosen_exe,
            "apis": pe.graphics_apis(str(root / chosen_exe)),
            "size": (root / chosen_exe).stat().st_size,
            "score": 0,
        }

    target = (root / selected["exe"]).parent if selected else None
    if selected:
        for kind in embedded_upscalers(root / selected["exe"]):
            if not inputs[kind]:
                inputs[kind].append(selected["exe"])
    return {
        "candidates": candidates[:6],
        "exe": selected["exe"] if selected else None,
        "apis": selected["apis"] if selected else [],
        "manual": manual,
        "target": str(target) if target else None,
        "inputs": {kind: sorted(paths)[:4] for kind, paths in inputs.items() if paths},
        "streamline": streamline_major(root / sorted(inputs["streamline"])[0]) if inputs["streamline"] else None,
        "anti_cheat": anti_cheat,
        "foreign": bool(target) and not (target / MANIFEST_DIR).exists() and any(
            (target / marker).exists() for marker in FOREIGN_MARKERS
        ),
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


def embedded_upscalers(exe: Path) -> set[str]:
    try:
        with open(exe, "rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
            return {kind for kind, needles in EMBEDDED.items() if any(data.find(n) != -1 for n in needles)}
    except (OSError, ValueError):
        return set()


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
