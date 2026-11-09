"""Durable checkpoints for managed scaler changes awaiting launch confirmation."""

import copy
import hashlib
import json
import os
import shutil
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path

from json_store import atomic_json_save

from .games import MANIFEST_DIR


class TransitionError(Exception):
    pass


# Files the game, OptiScaler, ReShade/Luma or REFramework rewrite while running. A change there is the game
# playing, not someone tampering with the checkpoint: it never blocks a commit, a rollback or the next change.
VOLATILE = frozenset({
    "optiscaler.log", "optiscaler.ini", "reshade.ini", "reshade.log", "reshade64.log",
    "re2_fw_config.txt", "re2_framework_log.txt", "re2_framework_log.prev.txt",
})


def _volatile(relative):
    return Path(relative).name.lower() in VOLATILE


class Checkpoints:
    def __init__(self, directory):
        self.directory = Path(directory) / "scaler-transitions"

    def _folder(self, appid):
        if self.directory.is_symlink():
            raise TransitionError("transition_unsafe_path")
        return self.directory / hashlib.sha256(str(appid).encode()).hexdigest()

    def _load(self, appid):
        folder = self._folder(appid)
        if folder.is_symlink():
            raise TransitionError("transition_conflict")
        try:
            data = json.loads((folder / "checkpoint.json").read_text())
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            raise TransitionError("transition_conflict") from None
        if data.get("appid") != str(appid):
            raise TransitionError("transition_conflict")
        return data

    def _save(self, data):
        atomic_json_save(str(self._folder(data["appid"]) / "checkpoint.json"), data)

    @staticmethod
    def _path(data, relative):
        root = Path(data["root"])
        part = Path(relative)
        if part.is_absolute() or not part.parts or any(p in ("..", ".") for p in part.parts):
            raise TransitionError("transition_unsafe_path")
        path = root / part
        if not path.is_relative_to(root):
            raise TransitionError("transition_unsafe_path")
        for candidate in (root, *[root.joinpath(*part.parts[:i]) for i in range(1, len(part.parts) + 1)]):
            if candidate.is_symlink():
                raise TransitionError("transition_unsafe_path")
        return path

    @staticmethod
    def _fingerprint(path):
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode):
            raise TransitionError("transition_unsafe_path")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return {"sha256": digest.hexdigest(), "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid}

    def _metadata_files(self, data):
        paths = set()
        for relative in data["metadata"]:
            folder = self._path(data, relative)
            if not folder.exists():
                continue
            if not folder.is_dir():
                raise TransitionError("transition_unsafe_path")
            for parent, dirs, files in os.walk(folder, followlinks=False):
                for name in [*dirs, *files]:
                    path = Path(parent) / name
                    rel = path.relative_to(data["root"]).as_posix()
                    self._path(data, rel)
                    if path.is_file():
                        paths.add(rel)
                    if len(paths) > 2048:
                        raise TransitionError("transition_too_large")
        return paths

    def _verify(self, data):
        if self._metadata_files(data) - data["files"].keys():
            raise TransitionError("transition_conflict")
        for relative, saved in data["files"].items():
            current = self._fingerprint(self._path(data, relative))
            if current != saved["expected"]:
                if not _volatile(relative):
                    raise TransitionError("transition_conflict")
                saved["expected"] = current

    def _rebaseline(self, data):
        """Accept what is on disk now: a later rollback still returns every captured file to its `before`."""
        for relative in self._metadata_files(data) - data["files"].keys():
            data["files"][relative] = {"before": None, "expected": None, "key": hashlib.sha256(relative.encode()).hexdigest()}
        for item_path, item in data["files"].items():
            item["expected"] = self._fingerprint(self._path(data, item_path))

    def _capture(self, data, paths):
        for relative in sorted(set(paths)):
            path = self._path(data, relative)
            if relative in data["files"]:
                continue
            if len(data["files"]) >= 2048:
                raise TransitionError("transition_too_large")
            before = self._fingerprint(path)
            key = hashlib.sha256(relative.encode()).hexdigest()
            if before is not None:
                saved = self._folder(data["appid"]) / "files" / key
                if saved.is_symlink() or saved.parent.is_symlink():
                    raise TransitionError("transition_unsafe_path")
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, saved)
                if self._fingerprint(path) != before or self._fingerprint(saved)["sha256"] != before["sha256"]:
                    raise TransitionError("transition_conflict")
            data["files"][relative] = {"before": before, "expected": before, "key": key}
            for parent in path.parents:
                if parent == Path(data["root"]):
                    break
                name = parent.relative_to(data["root"]).as_posix()
                data["directories"].setdefault(name, parent.is_dir())
        self._save(data)

    def begin(self, appid, root, entry, restore, target=None, previous_mako=None, configuration=()):
        if self._load(appid) is not None:
            raise TransitionError("transition_pending")
        folder = self._folder(appid)
        if folder.exists():
            self._discard(folder)
        root_alias = str(Path(root).absolute())
        root = Path(root).resolve(strict=True)
        self.directory.mkdir(parents=True, exist_ok=True)
        folder.mkdir(mode=0o700)
        data = {"appid": str(appid), "token": uuid.uuid4().hex, "root": str(root), "root_alias": root_alias, "entry": copy.deepcopy(entry),
                "restore": copy.deepcopy(restore), "previous_mako": copy.deepcopy(previous_mako), "files": {}, "directories": {}, "metadata": []}
        try:
            self._save(data)
            if target is not None:
                target = Path(target).resolve(strict=True)
                relative = (target / MANIFEST_DIR).relative_to(root).as_posix()
                self._path(data, relative)
                data["metadata"].append(relative)
                manifest_path = self._path(data, relative + "/manifest.json")
                manifest = json.loads(manifest_path.read_text())
                paths = self._metadata_files(data)
                for name, digest in manifest.get("files", {}).items():
                    path = self._path(data, (target / name).relative_to(root).as_posix())
                    current = self._fingerprint(path)
                    if current is None or (digest is not None and current["sha256"] != digest and name not in configuration
                                           and not _volatile(name)):
                        raise TransitionError("transition_conflict")
                    paths.add(path.relative_to(root).as_posix())
                for name in manifest.get("backups", []):
                    self._path(data, (target / name).relative_to(root).as_posix())
                for name in ("OptiScaler.log",):
                    paths.add((target / name).relative_to(root).as_posix())
                self._capture(data, paths)
            return {"token": data["token"], "restore": data["restore"], "previous_mako": data["previous_mako"], "recovery": False}
        except BaseException:
            shutil.rmtree(folder)
            raise

    def pending(self, appid):
        return self._load(appid)

    @contextmanager
    def mutation(self, target, names):
        original_target = Path(target).absolute()
        target = original_target.resolve()
        matches = []
        if self.directory.exists():
            for folder in self.directory.iterdir():
                if folder.name.startswith("."):
                    if folder.name.startswith(".discard-") and not folder.is_symlink():
                        shutil.rmtree(folder, ignore_errors=True)
                    continue
                if folder.is_symlink() or not folder.is_dir():
                    raise TransitionError("transition_conflict")
                try:
                    data = json.loads((folder / "checkpoint.json").read_text())
                except (OSError, ValueError):
                    # Interrupted between creating the folder and its first save, or while clearing it.
                    self._discard(folder)
                    continue
                if original_target.is_relative_to(Path(data.get("root_alias", data["root"]))) or target.is_relative_to(Path(data["root"])):
                    if not target.is_relative_to(Path(data["root"])):
                        raise TransitionError("transition_unsafe_path")
                    matches.append(data)
        if not matches:
            yield
            return
        if len(matches) != 1:
            raise TransitionError("transition_conflict")
        data = matches[0]
        try:
            self._verify(data)
        except TransitionError:
            self._rebaseline(data)
        meta = (target / MANIFEST_DIR).relative_to(data["root"]).as_posix()
        if meta not in data["metadata"]:
            data["metadata"].append(meta)
        paths = {(target / name).relative_to(data["root"]).as_posix() for name in names}
        self._capture(data, paths | self._metadata_files(data))
        try:
            yield
        finally:
            for relative in self._metadata_files(data) - data["files"].keys():
                data["files"][relative] = {"before": None, "expected": None, "key": hashlib.sha256(relative.encode()).hexdigest()}
                for parent in self._path(data, relative).parents:
                    if parent == Path(data["root"]):
                        break
                    data["directories"].setdefault(parent.relative_to(data["root"]).as_posix(), False)
            for relative, item in data["files"].items():
                item["expected"] = self._fingerprint(self._path(data, relative))
            self._save(data)

    def finish(self, appid, token, rollback):
        data = self._load(appid)
        if not data or data.get("token") != token:
            raise TransitionError("transition_token")
        if rollback:
            self._verify(data)
            for relative, item in data["files"].items():
                path = self._path(data, relative)
                before = item["before"]
                if before is None:
                    path.unlink(missing_ok=True)
                else:
                    source = self._folder(appid) / "files" / item["key"]
                    if self._fingerprint(source)["sha256"] != before["sha256"]:
                        raise TransitionError("transition_conflict")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temp = path.with_name(".pdc-restore-" + uuid.uuid4().hex)
                    try:
                        shutil.copyfile(source, temp)
                        os.chmod(temp, before["mode"])
                        if (temp.stat().st_uid, temp.stat().st_gid) != (before["uid"], before["gid"]):
                            os.chown(temp, before["uid"], before["gid"])
                        os.replace(temp, path)
                    finally:
                        temp.unlink(missing_ok=True)
                item["expected"] = self._fingerprint(path)
                self._save(data)
            for relative, existed in sorted(data["directories"].items(), key=lambda pair: len(pair[0]), reverse=True):
                if not existed:
                    try:
                        self._path(data, relative).rmdir()
                    except OSError:
                        pass
        return data

    def clear(self, appid):
        self._discard(self._folder(appid))

    def _discard(self, folder):
        """Rename first, so an interrupted removal never leaves a half checkpoint behind."""
        if folder.is_symlink():
            raise TransitionError("transition_unsafe_path")
        if not folder.exists():
            return
        trash = folder.with_name(f".discard-{uuid.uuid4().hex}")
        os.replace(folder, trash)
        shutil.rmtree(trash, ignore_errors=True)
