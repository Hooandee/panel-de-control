"""lsfg-vk: Lossless Scaling's frame generation as a Vulkan layer, for any game.

The layer is implicit: once installed it loads everywhere and only acts when a profile is picked,
by `LSFGVK_PROFILE` (the profile's name, which Panel puts in the game's launch options) or by
`active_in`, which matches binary, .exe or process names, never a Steam appid. It needs `lsfg-vk.dll` from the
user's own copy of Lossless Scaling on Steam (branch `lsfg-vk`); upstream only searches the main
library, so Panel always writes the path it found. Panel owns the layer files it installed and the
config file it wrote, and leaves another tool's install or config alone.
"""

import json
import os
import shutil
from pathlib import Path

from . import games
from .assets import sha256

LOSSLESS_APPID = "993090"
DLL_NAME = "lsfg-vk.dll"
LAYER_FILES = (
    "lib/liblsfg-vk-layer.so",
    "lib/liblsfg-vk-layer.x86.so",
    "share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json",
    "share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.x86.json",
)
CONFIG = ".config/lsfg-vk/conf.toml"
MARKER = "# Managed by Panel de Control"
MULTIPLIERS = (2, 3, 4, 5, 6)
# lsfg-vk accepts 0.25-1.0; lower is faster and softer.
FLOW_SCALES = {"quality": 1.0, "balanced": 0.75, "performance": 0.5, "fastest": 0.25}
# lsfg-vk rejects a config without any [[profile]] and then fails every present (the game freezes).
PLACEHOLDER = "pdc-none"
PAUSED_LIMIT = 50
# Gamescope's own WSI layer and lsfg-vk fight over the swapchain inside a gamescope session.
LAUNCH_ENV = {"ENABLE_GAMESCOPE_WSI": "0"}


class LsfgError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def find_dll(home: str) -> Path | None:
    for library in games.library_paths(home):
        candidate = library / "steamapps/common/Lossless Scaling" / DLL_NAME
        if candidate.is_file():
            return candidate
    return None


def lossless_installed(home: str) -> bool:
    return any((library / f"steamapps/appmanifest_{LOSSLESS_APPID}.acf").is_file() for library in games.library_paths(home))


class Lsfg:
    def __init__(self, home: str, state_dir: Path):
        self.home = Path(home)
        self.local = self.home / ".local"
        self.manifest_path = Path(state_dir) / "lsfg.json"
        self.config_path = self.home / CONFIG

    # ---- state -------------------------------------------------------------------------------
    def _manifest(self) -> dict:
        try:
            data = json.loads(self.manifest_path.read_text())
        except (OSError, ValueError):
            return {"files": {}, "profiles": {}}
        data.setdefault("files", {})
        data.setdefault("profiles", {})
        return data

    def _own(self, path: Path) -> None:
        """Files in the user's home stay the user's: Decky runs this as root."""
        if os.geteuid() != 0:
            return
        stat = self.home.stat()
        os.chown(path, stat.st_uid, stat.st_gid, follow_symlinks=False)

    def _save(self, data: dict) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(self.manifest_path)

    def _ours(self) -> bool:
        files = self._manifest()["files"]
        return bool(files) and all((self.local / f).is_file() for f in files)

    def _foreign(self) -> bool:
        """Another tool's layer or config: Panel reads it but never writes over it."""
        layer = (self.local / LAYER_FILES[2]).exists() and not self._manifest()["files"]
        try:
            config = self.config_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            config = None
        return layer or (config is not None and MARKER not in config.splitlines()[:1])

    def status(self) -> dict:
        dll = find_dll(str(self.home))
        return {
            "installed": self._ours(),
            "foreign": self._foreign(),
            "lossless": lossless_installed(str(self.home)),
            "dll": str(dll) if dll else None,
            "profiles": self._manifest()["profiles"],
            "foreign_backup": bool(self._manifest().get("foreign_backup")),
        }

    # ---- layer -------------------------------------------------------------------------------
    def install(self, unpacked: Path, version: str) -> dict:
        if self._foreign():
            raise LsfgError("lsfg_foreign")
        data = self._manifest()
        files = {}
        for relative in LAYER_FILES:
            source = unpacked / relative
            if not source.is_file():
                raise LsfgError("lsfg_archive")
            target = self.local / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            self._own(target)
            files[relative] = sha256(target)
        data.update(files=files, version=version)
        self._save(data)
        self._write_config(data)
        return self.status()

    def uninstall(self) -> dict:
        data = self._manifest()
        if not data["files"]:
            return self.status()
        kept = data.get("foreign_backup")
        for relative, digest in data["files"].items():
            path = self.local / relative
            if path.is_file() and (not digest or sha256(path) == digest):
                path.unlink()
        if self.config_path.is_file() and not self._foreign():
            self.config_path.unlink()
        self._save({"files": {}, "profiles": {}, **({"foreign_backup": kept} if kept else {})})
        return self.status()

    # ---- another tool's lsfg-vk --------------------------------------------------------------
    def adopt_foreign(self) -> dict:
        """Set another tool's layer and config aside, restorable, so Panel's own can go in."""
        if not self._foreign():
            raise LsfgError("lsfg_not_foreign")
        backup = self.manifest_path.parent / "lsfg-foreign"
        backup.mkdir(parents=True, exist_ok=True)
        moved = []
        for path in [*(self.local / f for f in LAYER_FILES), self.config_path]:
            if path.is_file():
                relative = path.relative_to(self.home).as_posix()
                (backup / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(backup / relative))
                moved.append(relative)
        data = self._manifest()
        data["foreign_backup"] = {"dir": str(backup), "items": moved}
        self._save(data)
        return self.status()

    def restore_foreign(self) -> dict:
        data = self._manifest()
        record = data.get("foreign_backup")
        if not record:
            raise LsfgError("lsfg_no_backup")
        if self._ours():
            raise LsfgError("lsfg_installed")
        backup = Path(record["dir"])
        for relative in record.get("items", []):
            source, target = backup / relative, self.home / relative
            if source.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
        shutil.rmtree(backup, ignore_errors=True)
        data.pop("foreign_backup", None)
        self._save(data)
        return self.status()

    # ---- per-game profiles -------------------------------------------------------------------
    def set_game(self, appid: str, name: str, config: dict | None, exe: str | None = None) -> dict:
        """Returns the environment the game's launch options must carry (empty when it is off)."""
        if not self._ours():
            raise LsfgError("lsfg_missing")
        data = self._manifest()
        paused = [a for a in data.get("paused", []) if a != appid]
        if config is None:
            # A running game still asks for its profile by name: keep it, generating nothing.
            if data["profiles"].pop(appid, None) is not None:
                paused.append(appid)
        else:
            multiplier = int(config.get("multiplier", 2))
            flow = str(config.get("flow", "balanced"))
            if multiplier not in MULTIPLIERS or flow not in FLOW_SCALES:
                raise LsfgError("lsfg_invalid")
            data["profiles"][appid] = {
                "name": str(name or appid)[:80],
                "multiplier": multiplier,
                "flow": flow,
                "performance": bool(config.get("performance", True)),
                "exe": Path(exe).name if exe else None,
            }
        data["paused"] = paused[-PAUSED_LIMIT:]
        self._save(data)
        self._write_config(data)
        env = {**LAUNCH_ENV, "LSFGVK_PROFILE": profile_name(appid)} if appid in data["profiles"] else {}
        return {"env": env, "profile": data["profiles"].get(appid)}

    def _write_config(self, data: dict) -> None:
        if self._foreign():
            raise LsfgError("lsfg_foreign")
        dll = find_dll(str(self.home))
        lines = [MARKER, "version = 2", "", "[global]", "allow_fp16 = true"]
        if dll:
            lines.append(f"dll = {_toml(str(dll))}")
        for appid in data.get("paused", []):
            if appid not in data["profiles"]:
                lines += ["", "[[profile]]", "name = " + _toml(profile_name(appid)), "multiplier = 1"]
        if not data["profiles"] and not data.get("paused"):
            lines += ["", "[[profile]]", "name = " + _toml(PLACEHOLDER)]
        for appid, profile in sorted(data["profiles"].items()):
            lines += ["", f"# {profile['name']}", "[[profile]]", "name = " + _toml(profile_name(appid))]
            if profile.get("exe"):
                lines.append(f"active_in = [{_toml(profile['exe'])}]")
            lines += [
                f"multiplier = {profile['multiplier']}",
                f"flow_scale = {FLOW_SCALES[profile['flow']]}",
                f"performance_mode = {'true' if profile['performance'] else 'false'}",
            ]
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._own(tmp)
        tmp.replace(self.config_path)


def profile_name(appid: str) -> str:
    """Spaceless so `LSFGVK_PROFILE=` needs no quoting in Steam's launch options."""
    return f"pdc-{appid}"


def _toml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
