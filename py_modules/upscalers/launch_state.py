"""Private receipts for restoring only launch arguments previously owned by Panel."""

import hashlib
import json
import os
import re
import threading
from pathlib import Path

from json_store import atomic_json_save

MAX_BYTES = 64 * 1024
OWNERS = {"lsfg", "mako", "upscaler"}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_APPID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")


def _text(value, limit):
    return isinstance(value, str) and len(value) <= limit and not any(c in value for c in "\0\r\n")


def validate(receipt):
    if not isinstance(receipt, dict) or set(receipt) not in ({"version", "env", "wrappers"}, {"version", "env", "wrappers", "pending"}) or type(receipt["version"]) is not int or receipt["version"] != 1:
        raise ValueError("launch_receipt_invalid")
    if "pending" in receipt and type(receipt["pending"]) is not bool:
        raise ValueError("launch_receipt_invalid")
    env, wrappers = receipt["env"], receipt["wrappers"]
    if not isinstance(env, list) or len(env) > 32 or not isinstance(wrappers, dict) or set(wrappers) != {"before", "applied", "added"}:
        raise ValueError("launch_receipt_invalid")
    seen = set()
    for item in env:
        if not isinstance(item, dict) or set(item) != {"name", "before", "applied"}:
            raise ValueError("launch_receipt_invalid")
        name = item["name"]
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name in seen:
            raise ValueError("launch_receipt_invalid")
        seen.add(name)
        if (item["before"] is not None and not _text(item["before"], 8192)) or not _text(item["applied"], 8192):
            raise ValueError("launch_receipt_invalid")
    for tokens in wrappers.values():
        if not isinstance(tokens, list) or len(tokens) > 64 or any(not _text(token, 512) for token in tokens):
            raise ValueError("launch_receipt_invalid")
    try:
        encoded = json.dumps(receipt, ensure_ascii=True).encode()
    except (TypeError, ValueError, RecursionError):
        raise ValueError("launch_receipt_invalid") from None
    if len(encoded) > MAX_BYTES:
        raise ValueError("launch_receipt_invalid")
    return json.loads(encoded)


class LaunchReceipts:
    def __init__(self, state_dir: Path):
        self.directory = Path(state_dir) / "launch-receipts"
        self._lock = threading.RLock()

    def _path(self, appid, owner):
        if not isinstance(appid, str) or not _APPID.fullmatch(appid) or not isinstance(owner, str) or owner not in OWNERS:
            raise ValueError("launch_receipt_invalid")
        if self.directory.is_symlink():
            raise ValueError("launch_receipt_conflict")
        return self.directory / f"{hashlib.sha256(appid.encode()).hexdigest()}-{owner}.json"

    def get(self, appid, owner):
        with self._lock:
            path = self._path(appid, owner)
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as handle:
                    data = handle.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    return None
                return validate(json.loads(data))
            except (OSError, ValueError, UnicodeError, RecursionError):
                return None

    def set(self, appid, owner, receipt):
        with self._lock:
            path = self._path(appid, owner)
            clean = validate(receipt) if receipt is not None else None
            if path.is_symlink():
                raise ValueError("launch_receipt_conflict")
            if clean is None:
                path.unlink(missing_ok=True)
                return True
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            atomic_json_save(str(path), clean)
            return True
