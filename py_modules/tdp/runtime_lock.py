import json
import os


class RuntimeSafetyLock:
    def __init__(self, path: str | None = None) -> None:
        self._path = path

    def load(self) -> str | None:
        if not self._path:
            return None
        try:
            with open(self._path, encoding="utf-8") as handle:
                detail = handle.read(4096).strip()
        except OSError:
            return None
        return detail or None

    def persist(self, detail: str) -> bool:
        if not self._path:
            return True
        directory = os.path.dirname(self._path)
        temporary = f"{self._path}.tmp-{os.getpid()}"
        try:
            os.makedirs(directory, mode=0o700, exist_ok=True)
            with open(temporary, "w", encoding="utf-8") as handle:
                handle.write(str(detail)[:4096])
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
            return True
        except OSError:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            return False

    def load_payload(self) -> dict | None:
        detail = self.load()
        if detail is None:
            return None
        try:
            payload = json.loads(detail)
        except (TypeError, ValueError):
            return {"state": detail, "detail": detail}
        if not isinstance(payload, dict) or not isinstance(payload.get("state"), str):
            return {"state": detail, "detail": detail}
        return payload

    def persist_payload(self, payload: dict) -> bool:
        try:
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return False
        return self.persist(encoded)

    def clear(self) -> bool:
        if not self._path:
            return True
        try:
            os.unlink(self._path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False
