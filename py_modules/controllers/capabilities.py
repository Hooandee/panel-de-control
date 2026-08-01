"""Strict, JSON-safe descriptions of controller capability surfaces."""

import math


AVAILABILITY = {"supported", "experimental", "unavailable"}
APPLY = {"hot", "recreate", "next_launch", "read_only"}
READBACK = {"exact", "accepted", "observed", "none"}
EVIDENCE = {"upstream", "physical", "upstream_and_physical", "unknown"}
SCOPES = {"global", "game"}

_INVALID = object()
_MAX_FIELD_NESTING = 2


def surface(
    owner: str,
    availability: str,
    *,
    fields: dict,
    scope: tuple[str, ...],
    apply: str,
    readback: str,
    evidence: str,
    reason: str | None = None,
) -> dict:
    value = {
        "owner": owner,
        "availability": availability,
        "fields": fields,
        "scope": list(scope),
        "apply": apply,
        "readback": readback,
        "evidence": evidence,
    }
    if reason is not None:
        value["reason"] = reason
    return value


def report(device_key: str | None, manager: str, surfaces: dict[str, dict]) -> dict:
    return {
        "device_key": device_key,
        "manager": manager,
        "surfaces": surfaces,
    }


def _clean_json_value(value, depth: int = 0):
    if depth > _MAX_FIELD_NESTING:
        return _INVALID
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _INVALID
    if isinstance(value, list):
        clean = []
        for item in value:
            cleaned_item = _clean_json_value(item, depth + 1)
            if cleaned_item is _INVALID:
                return _INVALID
            clean.append(cleaned_item)
        return clean
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            if not isinstance(key, str):
                return _INVALID
            cleaned_item = _clean_json_value(item, depth + 1)
            if cleaned_item is _INVALID:
                return _INVALID
            clean[key] = cleaned_item
        return clean
    return _INVALID


def _clean_surface(value) -> dict | None:
    if not isinstance(value, dict):
        return None

    owner = value.get("owner")
    availability = value.get("availability")
    fields = value.get("fields")
    scope = value.get("scope")
    apply = value.get("apply")
    readback = value.get("readback")
    evidence = value.get("evidence")
    reason = value.get("reason")

    if not isinstance(owner, str) or not owner:
        return None
    if not isinstance(availability, str) or availability not in AVAILABILITY:
        return None
    if not isinstance(fields, dict):
        return None
    if not isinstance(scope, (list, tuple)) or any(
        not isinstance(item, str) or item not in SCOPES for item in scope
    ):
        return None
    if not isinstance(apply, str) or apply not in APPLY:
        return None
    if not isinstance(readback, str) or readback not in READBACK:
        return None
    if not isinstance(evidence, str) or evidence not in EVIDENCE:
        return None
    if reason is not None and (not isinstance(reason, str) or not reason):
        return None

    clean_fields = {}
    for name, field_value in fields.items():
        if not isinstance(name, str):
            return None
        clean_value = _clean_json_value(field_value)
        if clean_value is _INVALID:
            return None
        clean_fields[name] = clean_value

    clean = {
        "owner": owner,
        "availability": availability,
        "fields": clean_fields,
        "scope": list(scope),
        "apply": apply,
        "readback": readback,
        "evidence": evidence,
    }
    if reason is not None:
        clean["reason"] = reason
    return clean


def clean_report(value) -> dict:
    if not isinstance(value, dict):
        return report(None, "unknown", {})

    raw_device_key = value.get("device_key")
    device_key = raw_device_key if isinstance(raw_device_key, str) else None
    raw_manager = value.get("manager")
    manager = raw_manager if isinstance(raw_manager, str) and raw_manager else "unknown"
    raw_surfaces = value.get("surfaces")
    if not isinstance(raw_surfaces, dict):
        return report(device_key, manager, {})

    surfaces = {}
    for name, raw_surface in raw_surfaces.items():
        if not isinstance(name, str) or not name:
            continue
        clean_surface = _clean_surface(raw_surface)
        if clean_surface is not None:
            surfaces[name] = clean_surface
    return report(device_key, manager, surfaces)
