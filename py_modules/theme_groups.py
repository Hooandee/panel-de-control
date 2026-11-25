"""Groups shared by every theme: hand-picked lists and rule groups, stored per Steam account.

Mirrors src/groups/normalize.ts: both sides accept and drop the same records, so a bad record never costs the rest.
Rules are evaluated in the frontend; here they are only checked for shape and size.
"""

import json
import re
from pathlib import Path

GROUP_ID = re.compile(r"^[A-Za-z0-9:_-]{1,64}$")
ACCOUNT = re.compile(r"^\d{1,20}$")
TAG = re.compile(r"^[\x20-\x7E]{1,80}$")
RULE_TYPES = frozenset((
    "installed", "collection", "group", "name", "kind", "deckCompat", "steamosCompat", "tags", "features",
    "playtime", "lastPlayed", "released", "purchased", "size", "review", "achievements", "friends",
    "familyShared", "demo", "comingSoon", "streamable", "sdCard", "installFolder", "games", "all",
))
MAX_GROUPS = 100
MAX_MANUAL_GAMES = 200
MAX_RULES_PER_LEVEL = 32
MAX_DEPTH = 3
MAX_NAME = 40
MAX_PARAMS_BYTES = 4096
MAX_ACCOUNTS = 16


def _app_ids(value, limit):
    if not isinstance(value, list):
        raise ValueError("invalid_apps")
    out = []
    for item in value:
        if isinstance(item, int) and not isinstance(item, bool) and 0 < item < 2**32 and item not in out:
            out.append(item)
    return out[:limit]


def _rule(value, depth):
    if not isinstance(value, dict) or value.get("type") not in RULE_TYPES or not isinstance(value.get("inverted"), bool):
        return None
    if value["type"] == "all":
        if depth >= MAX_DEPTH:
            return None
        nested = rule_set(value.get("params"), depth + 1)
        return {"type": "all", "inverted": value["inverted"], "params": nested} if nested else None
    params = value.get("params")
    if not isinstance(params, dict):
        return None
    try:
        text = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None
    if len(text) > MAX_PARAMS_BYTES:
        return None
    return {"type": value["type"], "inverted": value["inverted"], "params": json.loads(text)}


def rule_set(value, depth=0):
    if not isinstance(value, dict) or value.get("mode") not in ("all", "any") or not isinstance(value.get("rules"), list):
        return None
    rules = [rule for rule in (_rule(item, depth) for item in value["rules"][:MAX_RULES_PER_LEVEL]) if rule]
    return {"mode": value["mode"], "rules": rules}


def normalize_group(value):
    if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not GROUP_ID.fullmatch(value["id"]):
        raise ValueError("invalid_group")
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("invalid_name")
    kind = value.get("kind")
    if kind not in ("manual", "rules"):
        raise ValueError("invalid_kind")
    picked = _app_ids(value.get("appIds"), MAX_MANUAL_GAMES)
    group = {
        "id": value["id"],
        "name": name.strip()[:MAX_NAME],
        "kind": kind,
        "appIds": picked if kind == "manual" else [],
        "added": _app_ids(value.get("added") or [], MAX_MANUAL_GAMES),
        "hidden": _app_ids(value.get("hidden") or [], MAX_MANUAL_GAMES),
    }
    if kind == "rules":
        rules = rule_set(value.get("rules"))
        if rules is None:
            raise ValueError("invalid_rules")
        group["rules"] = rules
    include = value.get("include")
    if kind == "rules" and isinstance(include, list):
        kinds = list(dict.fromkeys(k for k in include if isinstance(k, str) and k in ("software", "music", "tool", "video", "other")))
        if kinds:
            group["include"] = kinds
    for key in ("importedFrom", "legacyId"):
        if isinstance(value.get(key), str) and TAG.fullmatch(value[key]):
            group[key] = value[key]
    return group


def records(value):
    """Valid groups in order; duplicates, bad records and anything past the limit are dropped."""
    out, seen = [], set()
    for item in value if isinstance(value, list) else []:
        try:
            group = normalize_group(item)
        except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
            # A hand-edited or damaged record costs only itself.
            continue
        if group["id"] in seen:
            continue
        seen.add(group["id"])
        out.append(group)
        if len(out) >= MAX_GROUPS:
            break
    return out


def valid_account(account):
    return isinstance(account, str) and bool(ACCOUNT.fullmatch(account))


def store(value):
    """Every account's groups from the settings value, cleaned."""
    if not isinstance(value, dict):
        return {}
    return {account: records(groups) for account, groups in list(value.items())[:MAX_ACCOUNTS] if valid_account(account)}


def summary(value):
    accounts = store(value)
    groups = [group for account in accounts.values() for group in account]
    return {
        "accounts": len(accounts),
        "manual": sum(group["kind"] == "manual" for group in groups),
        "rules": sum(group["kind"] == "rules" for group in groups),
        "imported": sum("importedFrom" in group for group in groups),
    }


def read_tab_master(settings_dir, account):
    """Tab Master's tabs for one Steam account, as it stored them, or [] when it is not installed."""
    path = Path(settings_dir) / "TabMaster" / "settings.json"
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    users = data.get("usersDict") if isinstance(data, dict) else None
    user = users.get(account) if isinstance(users, dict) else None
    tabs = user.get("tabs") if isinstance(user, dict) else None
    if not isinstance(tabs, dict):
        return []
    return [dict(tab, id=tab_id) for tab_id, tab in list(tabs.items())[:200] if isinstance(tab, dict)]
