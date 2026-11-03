"""Heroic and Lutris games added to Steam: the shortcut points at the launcher, not at the game.

The real install folder, executable and the place where the launcher keeps per-game environment
come from each launcher's own files (paths as in Heroic's and Lutris' sources). Overrides go there,
because Steam's launch options stop at the launcher process (and at the Flatpak sandbox).
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

HEROIC_DIRS = (".config/heroic", ".var/app/com.heroicgameslauncher.hgl/config/heroic")
LUTRIS_DIRS = (  # (config dir, data dir); Lutris falls back to the data dir when ~/.config/lutris is missing
    (".config/lutris", ".local/share/lutris"),
    (".var/app/net.lutris.Lutris/config/lutris", ".var/app/net.lutris.Lutris/data/lutris"),
)
_HEROIC_URL = re.compile(r"heroic://launch(?:\?appName=([^&\"'\s]+)&runner=([\w-]+)|/(?:([\w-]+)/)?([^\"'\s/]+))")
_HEROIC_WRAPPER = re.compile(r"([\w-]+?)-(.+)\.desktop$")
_LUTRIS_ID = re.compile(r"lutris:rungameid/(\d+)")
_LUTRIS_SCRIPT = re.compile(r"lutris-(.+)\.sh$")
ENV_KEY = "WINEDLLOVERRIDES"


@dataclass(frozen=True)
class LauncherGame:
    launcher: str  # "heroic" | "lutris"
    key: str  # Heroic appName or Lutris game id
    name: str
    root: Path
    exe: str | None  # relative to root
    native: bool
    config: Path  # file Panel edits to add the overrides


def identify(exe: str, launch_options: str) -> tuple[str, str, str | None] | None:
    """(launcher, game key, runner) from a Steam shortcut, or None for anything else."""
    text = f"{exe} {launch_options}"
    match = _HEROIC_URL.search(text)
    if match:
        if match.group(1):
            return "heroic", match.group(1), match.group(2)
        return "heroic", match.group(4), match.group(3)
    wrapper = _HEROIC_WRAPPER.search(exe.strip().strip('"'))
    if wrapper and "heroic" in exe.lower():
        return "heroic", wrapper.group(2), wrapper.group(1)
    match = _LUTRIS_ID.search(text)
    if match:
        return "lutris", match.group(1), None
    script = _LUTRIS_SCRIPT.search(exe.strip().strip('"'))
    if script:
        return "lutris", "slug:" + script.group(1), None
    return None


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


def _relative(root: Path, exe: str | None) -> str | None:
    if not exe:
        return None
    path = Path(exe)
    if not path.is_absolute():
        return path.as_posix() if (root / path).is_file() else None
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _heroic_entry(base: Path, app: str, runner: str | None) -> tuple[str, Path, str | None, bool] | None:
    if runner in (None, "legendary"):
        info = (_json(base / "legendaryConfig/legendary/installed.json") or {}).get(app)
        if isinstance(info, dict) and info.get("install_path"):
            root = Path(info["install_path"])
            native = str(info.get("platform", "")).lower() in ("linux", "mac")
            return str(info.get("title") or app), root, _relative(root, info.get("executable")), native
    if runner in (None, "gog"):
        for info in (_json(base / "gog_store/installed.json") or {}).get("installed", []):
            if isinstance(info, dict) and str(info.get("appName")) == app and info.get("install_path"):
                root = Path(info["install_path"])
                tasks = (_json(root / f"goggame-{app}.info") or {}).get("playTasks") or []
                primary = next((t for t in tasks if isinstance(t, dict) and t.get("isPrimary")), None)
                return app, root, _relative(root, (primary or {}).get("path")), info.get("platform") == "linux"
    if runner in (None, "nile"):
        for info in _json(base / "nile_config/nile/installed.json") or []:
            if isinstance(info, dict) and info.get("id") == app and info.get("path"):
                root = Path(info["path"])
                command = ((_json(root / "fuel.json") or {}).get("Main") or {}).get("Command")
                return app, root, _relative(root, command), False
    if runner in (None, "sideload"):
        for info in (_json(base / "sideload_apps/library.json") or {}).get("games", []):
            if isinstance(info, dict) and info.get("app_name") == app:
                install = info.get("install") or {}
                exe = Path(str(install.get("executable") or ""))
                if exe.is_absolute():
                    return (str(info.get("title") or app), exe.parent, exe.name,
                            str(install.get("platform", "")).lower() == "linux")
    return None


def _lutris_row(data: Path, key: str) -> tuple[str, str, str] | None:
    """(name, slug, configpath) from pga.db; sqlite3 may be missing from the plugin's runtime."""
    try:
        import sqlite3
    except ImportError:
        return None
    column, value = ("slug", key[5:]) if key.startswith("slug:") else ("id", key)
    try:
        with sqlite3.connect(f"file:{data / 'pga.db'}?mode=ro", uri=True) as db:
            row = db.execute(f"SELECT name, slug, configpath FROM games WHERE {column} = ?", (value,)).fetchone()
    except sqlite3.Error:
        return None
    return (str(row[0]), str(row[1]), str(row[2])) if row and row[2] else None


def _yaml_scalar(text: str, section: str, key: str) -> str | None:
    """`key` under the top-level `section` of a Lutris game file (plain block YAML)."""
    current = None
    for line in text.splitlines():
        if line and not line[0].isspace():
            current = line.split(":", 1)[0].strip()
        elif current == section:
            stripped = line.strip()
            if stripped.startswith(f"{key}:"):
                value = stripped.split(":", 1)[1].strip()
                return value.strip("'\"") or None
    return None


def find(home: str, launcher: str, key: str, runner: str | None = None) -> LauncherGame | None:
    if launcher == "heroic":
        for directory in HEROIC_DIRS:
            base = Path(home) / directory
            entry = _heroic_entry(base, key, runner)
            if entry and entry[1].is_dir():
                name, root, exe, native = entry
                return LauncherGame("heroic", key, name, root, exe, native, base / "GamesConfig" / f"{key}.json")
        return None
    for config_dir, data_dir in LUTRIS_DIRS:
        config, data = Path(home) / config_dir, Path(home) / data_dir
        row = _lutris_row(data, key)
        if not row:
            continue
        games_dir = (config if config.is_dir() else data) / "games"
        path = games_dir / f"{row[2]}.yml"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        exe = _yaml_scalar(text, "game", "exe")
        if not exe:
            continue
        exe_path = Path(exe)
        if not exe_path.is_absolute():
            prefix = _yaml_scalar(text, "game", "prefix")
            exe_path = Path(prefix or "") / exe
        native = exe_path.suffix.lower() != ".exe"
        return LauncherGame("lutris", key, row[0], exe_path.parent, exe_path.name, native, path)
    return None


# ---- overrides --------------------------------------------------------------------------------

def _merge(existing: str, dlls: list[str], remove: bool) -> str:
    parts = [p for p in existing.split(";") if p.strip()] if existing else []
    kept = [p for p in parts if p.split("=", 1)[0].strip() not in dlls]
    if not remove:
        kept.append(f"{','.join(dlls)}=n,b")
    return ";".join(kept)


def _heroic_write(game: LauncherGame, dlls: list[str], remove: bool) -> None:
    data = _json(game.config) or {}
    settings = data.setdefault(game.key, {})
    env = [e for e in settings.get("enviromentOptions") or [] if isinstance(e, dict)]
    current = next((e for e in env if e.get("key") == ENV_KEY), None)
    value = _merge(str(current.get("value", "")) if current else "", dlls, remove)
    env = [e for e in env if e.get("key") != ENV_KEY]
    if value:
        env.append({"key": ENV_KEY, "value": value})
    settings["enviromentOptions"] = env
    game.config.parent.mkdir(parents=True, exist_ok=True)
    game.config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _lutris_write(game: LauncherGame, dlls: list[str], remove: bool) -> None:
    """Adds or drops `dll: n,b` lines under `wine:` → `overrides:`, leaving everything else as is."""
    lines = game.config.read_text(encoding="utf-8").splitlines()
    wine = next((i for i, l in enumerate(lines) if l.rstrip() == "wine:"), None)
    if wine is None:
        lines += ["wine:", "  overrides:"]
        wine = len(lines) - 2
    end = next((i for i in range(wine + 1, len(lines)) if lines[i] and not lines[i][0].isspace()), len(lines))
    overrides = next((i for i in range(wine + 1, end) if lines[i].strip() == "overrides:"), None)
    if overrides is None:
        lines.insert(wine + 1, "  overrides:")
        overrides, end = wine + 1, end + 1
    block_end = overrides + 1
    while block_end < end and lines[block_end].startswith("    "):
        block_end += 1
    block = [l for l in lines[overrides + 1:block_end] if l.strip().split(":", 1)[0].strip("'\"") not in dlls]
    if not remove:
        block += [f"    {dll}: n,b" for dll in dlls]
    lines[overrides + 1:block_end] = block
    if not block:
        del lines[overrides]
    game.config.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_overrides(game: LauncherGame, dlls: list[str], remove: bool = False) -> None:
    (_heroic_write if game.launcher == "heroic" else _lutris_write)(game, dlls, remove)
