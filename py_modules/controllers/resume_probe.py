"""Read-only evidence of what a resume did to the controller stack.

Panel de Control never touches the controller on resume (HHD/kernel re-grab races).
This only observes: InputPlumber's composite device and capabilities against the last
reading before the suspend, the hidraw/input nodes and InputPlumber's udev rules.
"""
import os
import re

from controllers.detect import INPUTPLUMBER

IP_RESUME_FIXED_IN = (0, 84, 0)
# The Ally MCU re-enumerates on resume; InputPlumber before 0.84.0 can leave its
# udev hide rules on the old hidraw numbers and the recreated pad hidden.
ALLY_DEVICE_KEYS = frozenset({"rog_ally", "rog_ally_x", "rog_xbox_ally", "rog_xbox_ally_x"})
RULES_DIR = "/run/udev/rules.d"
_NODE_LIMIT = 32
_RULE_LIMIT = 32
_UEVENT_BYTES = 2048
_RULE_NODE = re.compile(r"(hidraw|event)(\d+)")


def parse_version(text) -> tuple | None:
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", str(text or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def capability_diff(before, after) -> dict:
    before, after = list(before or ()), list(after or ())
    return {
        "lost": [cap for cap in before if cap not in after],
        "gained": [cap for cap in after if cap not in before],
    }


def advisory(device_key, version, before, after) -> dict | None:
    """A known-bug flag, never an action: Ally family, InputPlumber older than the fix,
    and capabilities that were there before the suspend are gone after it."""
    parsed = parse_version(version)
    if device_key not in ALLY_DEVICE_KEYS or parsed is None or parsed >= IP_RESUME_FIXED_IN:
        return None
    lost = capability_diff(before, after)["lost"]
    if not lost:
        return None
    return {
        "code": "inputplumber_resume_capability_loss",
        "reason": "known_inputplumber_resume_bug",
        "action": "update_inputplumber",
        "installed": version,
        "fixed_in": ".".join(str(part) for part in IP_RESUME_FIXED_IN),
        "capabilities_lost": len(lost),
    }


def _read(path, limit=_UEVENT_BYTES):
    try:
        with open(path, "rb") as handle:
            return handle.read(limit).decode("utf-8", "replace")
    except OSError:
        return None


def _hid_id(sys_root, name):
    uevent = _read(os.path.join(sys_root, "class", "hidraw", name, "device", "uevent"))
    match = re.search(r"^HID_ID=[0-9A-Fa-f]+:([0-9A-Fa-f]+):([0-9A-Fa-f]+)$", uevent or "", re.M)
    return f"{match.group(1)[-4:].lower()}:{match.group(2)[-4:].lower()}" if match else None


def _input_id(sys_root, name):
    base = os.path.join(sys_root, "class", "input", name, "device", "id")
    vendor, product = _read(os.path.join(base, "vendor")), _read(os.path.join(base, "product"))
    if not vendor or not product:
        return None
    return f"{vendor.strip().lower().zfill(4)[-4:]}:{product.strip().lower().zfill(4)[-4:]}"


def _owner(st):
    try:
        import grp
        import pwd

        user = pwd.getpwuid(st.st_uid).pw_name
        group = grp.getgrgid(st.st_gid).gr_name
        return f"{user}:{group}"
    except Exception:  # noqa: BLE001
        return f"{st.st_uid}:{st.st_gid}"


def _node_rows(directory, prefix, klass, ident, sys_root):
    try:
        names = sorted(
            (n for n in os.listdir(directory) if re.fullmatch(rf"{prefix}\d+", n)),
            key=lambda n: int(n[len(prefix):]),
        )
    except OSError:
        return []
    rows = []
    for name in names[:_NODE_LIMIT]:
        try:
            st = os.stat(os.path.join(directory, name))
            real = os.path.realpath(os.path.join(sys_root, "class", klass, name))
        except OSError:
            continue
        mode = st.st_mode & 0o777
        rows.append({
            "node": name,
            "mode": f"{mode:04o}",
            "owner": _owner(st),
            "id": ident(sys_root, name),
            "virtual": "/virtual/" in real,
            "hidden": mode == 0,
        })
    return rows


def nodes(dev_root="/dev", sys_root="/sys") -> list:
    return [
        *_node_rows(dev_root, "hidraw", "hidraw", _hid_id, sys_root),
        *_node_rows(os.path.join(dev_root, "input"), "event", "input", _input_id, sys_root),
    ]


def udev_rules(rules_dir=RULES_DIR, dev_root="/dev") -> list:
    try:
        names = sorted(n for n in os.listdir(rules_dir) if "inputplumber" in n.lower())
    except OSError:
        return []
    rows = []
    for name in names[:_RULE_LIMIT]:
        try:
            mtime = int(os.stat(os.path.join(rules_dir, name)).st_mtime)
        except OSError:
            continue
        row = {"name": name, "mtime": mtime}
        node = _RULE_NODE.search(name)
        if node:
            target = node.group(0)
            parent = os.path.join(dev_root, "input") if node.group(1) == "event" else dev_root
            row["node"] = target
            row["node_present"] = os.path.exists(os.path.join(parent, target))
        rows.append(row)
    return rows


def _composite_index(path):
    match = re.search(r"CompositeDevice(\d+)$", path or "")
    return int(match.group(1)) if match else None


def _target_names(paths):
    """Kinds only (`keyboard0` would be redacted as a serial)."""
    if paths is None:
        return None
    return [re.sub(r"\d+$", "", str(path).rsplit("/", 1)[-1]) for path in paths]


def collect(
    dbus, *, before, before_path, version, device_key, elapsed_s=None,
    dev_root="/dev", sys_root="/sys", rules_dir=RULES_DIR,
) -> dict:
    """One bounded read-only snapshot; `dbus` is a fresh driver so its discovery is not
    the cached path from before the suspend. Paths are reduced to their index because
    the free-text redaction would turn `CompositeDevice7` into a serial."""
    after = dbus.capabilities()
    last = (dbus.diagnostics() or {}).get("last_operation") or {}
    result = {
        "manager": INPUTPLUMBER,
        "version": version,
        "device_key": device_key,
        "elapsed_s": elapsed_s,
        "composite_before": _composite_index(before_path),
        "composite_after": _composite_index(dbus.composite_path()),
        "caps_read_ok": bool(last.get("ok")),
        "caps_before": list(before or ()),
        "caps_after": after,
        "targets": _target_names(dbus.target_devices()),
        "nodes": nodes(dev_root, sys_root),
        "udev_rules": udev_rules(rules_dir, dev_root),
    }
    diff = capability_diff(before, after)
    result["caps_lost"] = diff["lost"]
    result["caps_gained"] = diff["gained"]
    result["advisory"] = advisory(device_key, version, before, after) if result["caps_read_ok"] else None
    return result
