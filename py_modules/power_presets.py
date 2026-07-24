"""Durable library of user power presets shown as quick-apply chips in Potencia.

Stores ONLY {order, hidden, custom}; the built-in preset watts (quiet/balanced/turbo)
are resolved in the frontend from the live TDP state (AC-aware), so this never caches
them. Built-in slugs can be reordered/hidden but not created/edited/deleted. Coercion
never raises — a malformed persisted file must not brick the panel."""
import json

from json_store import atomic_json_save

BUILTIN_IDS = ("quiet", "balanced", "turbo")
_MODES = ("estable", "auto", "custom")
_MAX_CUSTOM = 30


_ESTABLE = {"mode": "estable", "off2": 0, "off3": 0}


def _as_int(v, default):
    # OverflowError covers a JSON `1e309` → float('inf'); int(inf) would otherwise raise.
    try:
        return int(v)
    except (TypeError, ValueError, OverflowError):
        return default


def _clean_boost(raw):
    if not isinstance(raw, dict):
        return None
    if raw.get("mode") not in _MODES:
        return None
    return {"mode": raw["mode"],
            "off2": max(0, _as_int(raw.get("off2"), 0)),
            "off3": max(0, _as_int(raw.get("off3"), 0))}


def _clean_custom_entry(raw, min_w=1, max_w=1000):
    if not isinstance(raw, dict):
        raw = {}
    watts = max(int(min_w), min(_as_int(raw.get("watts"), 10), int(max_w)))
    name = raw.get("name")
    name = name.strip()[:40] if isinstance(name, str) else ""
    # A custom preset always carries a definite boost (estable = flat/no headroom by
    # default); "leave the boost untouched" is expressed by the built-ins (boost=null),
    # not a custom-preset option.
    return {"watts": watts,
            "icon": raw.get("icon") if isinstance(raw.get("icon"), str) else "bolt",
            "name": name,
            "boost": _clean_boost(raw.get("boost")) or dict(_ESTABLE)}


class PowerPresetStore:
    def __init__(self, path):
        self._path = path
        self._data = self._load()

    def _load(self):
        try:
            with open(self._path) as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        custom = {}
        raw_custom = raw.get("custom")
        if isinstance(raw_custom, dict):
            for cid, entry in raw_custom.items():
                if isinstance(cid, str) and cid.startswith("c"):
                    custom[cid] = _clean_custom_entry(entry)
        valid = set(BUILTIN_IDS) | set(custom)
        raw_order = raw.get("order") if isinstance(raw.get("order"), list) else []
        order, seen = [], set()
        for i in raw_order:
            if isinstance(i, str) and i in valid and i not in seen:
                order.append(i)
                seen.add(i)
        for b in BUILTIN_IDS:  # never lose a built-in
            if b not in seen:
                order.append(b)
                seen.add(b)
        for c in custom:  # nor a custom entry absent from a stale order
            if c not in seen:
                order.append(c)
                seen.add(c)
        # Enforce the custom cap on load too: a stale/hand-edited file with thousands of
        # entries would otherwise build thousands of focusable rows and freeze the QAM.
        # Keep the first _MAX_CUSTOM customs by display order; drop the rest everywhere.
        if len(custom) > _MAX_CUSTOM:
            keep = set([i for i in order if i in custom][:_MAX_CUSTOM])
            custom = {k: v for k, v in custom.items() if k in keep}
            order = [i for i in order if i in BUILTIN_IDS or i in keep]
        valid = set(BUILTIN_IDS) | set(custom)
        raw_hidden = raw.get("hidden") if isinstance(raw.get("hidden"), list) else []
        hidden = [i for i in raw_hidden if isinstance(i, str) and i in valid]
        highest = max((_as_int(c[1:], 0) for c in custom), default=0)
        seq = max(_as_int(raw.get("seq"), 0), highest)
        return {"order": order, "hidden": hidden, "custom": custom, "seq": seq}

    def _save(self):
        # On a write failure revert in-memory to what's on disk so a rejected mutation
        # can't linger as a fake success; re-raise so the RPC surfaces it.
        try:
            atomic_json_save(self._path, self._data)
        except OSError:
            self._data = self._load()
            raise

    def state(self):
        return {"order": list(self._data["order"]),
                "hidden": list(self._data["hidden"]),
                "custom": {k: dict(v) for k, v in self._data["custom"].items()}}

    def create(self, watts, icon, boost, name="", min_w=1, max_w=1000):
        if len(self._data["custom"]) >= _MAX_CUSTOM:
            return self.state()
        self._data["seq"] += 1
        cid = f"c{self._data['seq']}"
        self._data["custom"][cid] = _clean_custom_entry(
            {"watts": watts, "icon": icon, "name": name, "boost": boost}, min_w, max_w)
        self._data["order"].append(cid)
        self._save()
        return self.state()

    def update(self, cid, watts, icon, boost, name="", min_w=1, max_w=1000):
        if cid not in self._data["custom"]:
            return self.state()
        self._data["custom"][cid] = _clean_custom_entry(
            {"watts": watts, "icon": icon, "name": name, "boost": boost}, min_w, max_w)
        self._save()
        return self.state()

    def delete(self, cid):
        if cid in self._data["custom"]:
            del self._data["custom"][cid]
            self._data["order"] = [i for i in self._data["order"] if i != cid]
            self._data["hidden"] = [i for i in self._data["hidden"] if i != cid]
            self._save()
        return self.state()

    def move(self, cid, direction):
        order = self._data["order"]
        if cid in order:
            i = order.index(cid)
            j = i + (1 if int(direction) > 0 else -1)
            if 0 <= j < len(order):
                order[i], order[j] = order[j], order[i]
                self._save()
        return self.state()

    def set_hidden(self, cid, hidden):
        valid = set(BUILTIN_IDS) | set(self._data["custom"])
        if cid in valid:
            cur = set(self._data["hidden"])
            cur.add(cid) if hidden else cur.discard(cid)
            self._data["hidden"] = [i for i in self._data["order"] if i in cur]
            self._save()
        return self.state()
