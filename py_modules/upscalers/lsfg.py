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
import tempfile
import threading
import shutil
import shlex
import tomllib
from pathlib import Path

from . import games, ownership
from .assets import sha256
from .lsfg_logs import RuntimeLog

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
        self._lock = threading.RLock()
        self.home = Path(home)
        self.local = self.home / ".local"
        self.manifest_path = Path(state_dir) / "lsfg.json"
        self.config_path = self.home / CONFIG
        self.runtime_log = RuntimeLog(self.home)
        self._closed = False

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
        """Files in the user's home, and the folders made for them, stay the user's: Decky runs this as root."""
        ownership.own_with_parents(self.home, path)

    def _save(self, data: dict) -> None:
        tmp = self._stage_bytes(self.manifest_path, json.dumps(data, indent=1).encode())
        try:
            os.replace(tmp, self.manifest_path)
        finally:
            tmp.unlink(missing_ok=True)

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
        with self._lock:
            self._watch_log()
            dll = find_dll(str(self.home))
            return {
                "installed": self._ours(),
                "version": self._manifest().get("version") if self._ours() else None,
                "foreign": self._foreign(),
                "lossless": lossless_installed(str(self.home)),
                "dll": str(dll) if dll else None,
                "profiles": self._manifest()["profiles"],
                "foreign_backup": bool(self._manifest().get("foreign_backup")),
            }

    def _watch_log(self):
        if self._closed or self._foreign():
            return
        try:
            config = tomllib.loads(self.config_path.read_text())
            settings = config.get("global")
            if isinstance(settings, dict) and settings.get("log_file") == str(self.runtime_log.path):
                if not self.runtime_log.running and self.runtime_log.prepare():
                    self.runtime_log.start()
        except (OSError, ValueError):
            pass

    def report(self) -> dict:
        return {**self.status(), "runtime_log": self.runtime_log.report()}

    def close(self):
        self._closed = True
        self.runtime_log.close()

    # ---- layer -------------------------------------------------------------------------------
    def _safe_path(self, path: Path, root: Path) -> None:
        if path != root and root not in path.parents:
            raise LsfgError("lsfg_conflict")
        current = path
        while True:
            if current.is_symlink():
                raise LsfgError("lsfg_conflict")
            if current == root:
                break
            current = current.parent

    def _stage_bytes(self, path: Path, content: bytes, mode: int = 0o644) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".lsfg-", dir=path.parent)
        staged = Path(name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            staged.chmod(mode)
            if self.home in path.parents:
                self._own(staged)
            return staged
        except Exception:
            staged.unlink(missing_ok=True)
            raise

    def _check_owned(self, data: dict) -> None:
        for path in [*(self.local / name for name in LAYER_FILES), self.config_path]:
            self._safe_path(path, self.home)
        self._safe_path(self.manifest_path, self.manifest_path.parent)
        if self._foreign():
            raise LsfgError("lsfg_foreign")
        for relative in LAYER_FILES:
            target = self.local / relative
            if target.exists():
                digest = data["files"].get(relative)
                if not target.is_file() or not digest or sha256(target) != digest:
                    raise LsfgError("lsfg_conflict")
            elif relative in data["files"]:
                raise LsfgError("lsfg_conflict")

    def install(self, unpacked: Path, version: str, before_commit=None) -> dict:
        with self._lock:
            data = self._manifest()
            self._check_owned(data)
            preserve_config = bool(data["files"]) and self.config_path.is_file()
            paths = [*(self.local / name for name in LAYER_FILES), self.config_path, self.manifest_path]
            previous = {path: (path.read_bytes(), path.stat().st_mode & 0o777) if path.exists() else None
                        for path in paths}
            staged = {}
            publishing = False
            try:
                files = {}
                for relative in LAYER_FILES:
                    source = unpacked / relative
                    self._safe_path(source, unpacked)
                    if not source.is_file():
                        raise LsfgError("lsfg_archive")
                    target = self.local / relative
                    staged[target] = self._stage_bytes(target, source.read_bytes())
                    files[relative] = sha256(staged[target])
                    if files[relative] != sha256(source):
                        raise LsfgError("lsfg_archive")
                if before_commit is not None:
                    before_commit()
                self._check_owned(data)
                publishing = True
                for target, source in staged.items():
                    os.replace(source, target)
                data.update(files=files, version=version)
                self._save(data)
                if not preserve_config:
                    self._write_config(data)
            except Exception as error:
                failed = False
                if publishing:
                    for path, old in previous.items():
                        try:
                            if old is None:
                                path.unlink(missing_ok=True)
                            else:
                                restored = self._stage_bytes(path, old[0], old[1])
                                try:
                                    os.replace(restored, path)
                                finally:
                                    restored.unlink(missing_ok=True)
                        except OSError:
                            failed = True
                if failed:
                    raise LsfgError("lsfg_restore_failed") from error
                if isinstance(error, OSError):
                    raise LsfgError("lsfg_write_failed") from error
                raise
            finally:
                for path in staged.values():
                    path.unlink(missing_ok=True)
            return self.status()

    def uninstall(self) -> dict:
        with self._lock:
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
            # Games whose launch options still ask for a Panel profile that no longer exists.
            return {**self.status(), "cleared": sorted({*data["profiles"], *data.get("paused", [])})}

    # ---- another tool's lsfg-vk --------------------------------------------------------------
    def adopt_foreign(self) -> dict:
        """Set another tool's layer and config aside, restorable, so Panel's own can go in."""
        with self._lock:
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
            data["files"] = {name: digest for name, digest in data["files"].items()
                             if (Path(".local") / name).as_posix() not in moved}
            self._save(data)
            return self.status()

    def restore_foreign(self) -> dict:
        with self._lock:
            data = self._manifest()
            record = data.get("foreign_backup")
            if not record:
                raise LsfgError("lsfg_no_backup")
            if self._ours():
                raise LsfgError("lsfg_installed")
            backup = Path(record["dir"])
            left = []
            for relative in record.get("items", []):
                source, target = backup / relative, self.home / relative
                if not source.is_file():
                    continue
                if target.exists():
                    left.append(relative)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
            if left:
                # Something else wrote these since; the user's copies stay in the backup instead of being lost.
                data["foreign_backup"] = {**record, "items": left}
            else:
                shutil.rmtree(backup, ignore_errors=True)
                data.pop("foreign_backup", None)
            self._save(data)
            return self.status()

    # ---- per-game profiles -------------------------------------------------------------------
    def set_game(self, appid: str, name: str, config: dict | None, exe: str | None = None) -> dict:
        """Returns the environment the game's launch options must carry (empty when it is off)."""
        with self._lock:
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
            env = {**LAUNCH_ENV, "LSFGVK_PROFILE": profile_name(appid),
                   "LSFGVK_CONFIG": shlex.quote(str(self.config_path))} if appid in data["profiles"] else {}
            return {"env": env, "profile": data["profiles"].get(appid)}

    def _write_config(self, data: dict) -> None:
        if self._foreign():
            raise LsfgError("lsfg_foreign")
        dll = find_dll(str(self.home))
        lines = [MARKER, "version = 2", "", "[global]", "allow_fp16 = true"]
        if not self._closed and self.runtime_log.prepare():
            lines += ["log_level = \"info\"", f"log_file = {_toml(str(self.runtime_log.path))}"]
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
        tmp = self._stage_bytes(self.config_path, ("\n".join(lines) + "\n").encode())
        try:
            os.replace(tmp, self.config_path)
            self._watch_log()
        finally:
            tmp.unlink(missing_ok=True)


def profile_name(appid: str) -> str:
    """Spaceless so `LSFGVK_PROFILE=` needs no quoting in Steam's launch options."""
    return f"pdc-{appid}"


def _toml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
