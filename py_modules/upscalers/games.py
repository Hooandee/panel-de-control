"""Where an installed game lives, which executable creates its device and what it ships."""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from steam_cleaner import vdf

from . import pe

STATE_FULLY_INSTALLED = 4
STATE_UPDATE_RUNNING = 256 | 1024
MAX_DEPTH = 6
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
    "fsrfg": ("amd_fidelityfx_framegeneration_dx12.dll",),
    "xefg": ("libxess_fg.dll",),
}
ANTI_CHEAT = ("easyanticheat", "battleye", "eac_launcher", "beservice")
FOREIGN_MARKERS = ("OptiScaler.ini", "OptiScaler.log", "FRAMEGEN_PATCH", "helixsr-install.json")


@dataclass(frozen=True)
class Installed:
    appid: str
    name: str
    root: Path
    state_flags: int
    exe: str | None = None
    shortcut: bool = False
    native: bool = False


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
                exe = Path(_unquote(entry.get("exe")))
                start = Path(_unquote(entry.get("startdir"))) if _unquote(entry.get("startdir")) else exe.parent
                if not start.is_dir():
                    return None
                relative = None
                if exe.suffix.lower() == ".exe" and exe.is_file():
                    try:
                        relative = exe.resolve().relative_to(start.resolve()).as_posix()
                    except ValueError:
                        start, relative = exe.parent, exe.name
                return Installed(appid, str(entry.get("appname") or appid), start, STATE_FULLY_INSTALLED, relative, True)
    return None


def from_hint(appid: str, hint: dict | None) -> Installed | None:
    """A shortcut described by Steam's own app details, for when shortcuts.vdf does not list it."""
    if not isinstance(hint, dict):
        return None
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


def ships_upscaler(root: Path) -> bool:
    """Whether the game folder carries any DLSS, FSR or XeSS library."""
    names = {name for group in ("fsr31", "fsr2", "dlss", "xess") for name in INPUTS[group]}
    for _current, files in _walk(root):
        if any(file.lower() in names for file in files):
            return True
    return False


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
