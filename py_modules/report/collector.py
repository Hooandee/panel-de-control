"""Assemble a diagnostic bug-report bundle and scrub PII from it.

Split so the tricky parts are pure and unit-testable:
  - redact_text / redact_obj  - strip home paths, hostname, serial-like values
  - tail_logs                 - newest log files, size-capped, redacted
  - build_bundle              - assemble the final dict from already-fetched parts

main.py does the I/O (calls the get_*_state RPCs, reads the stores + log dir) and
hands the pieces here. The bundle is designed to be *diagnosable*: identity +
detected capabilities (many "X doesn't work" reports are "X has no write path on
your device") + a live state snapshot + the persisted stores + the tail of the
plugin logs where tracebacks land. Never raises: a report must go out even if a
piece is missing.
"""
from __future__ import annotations

import glob
import json
import os
import re

from sysfs import read_str

# Bump when the bundle shape changes so consumers can adapt.
SCHEMA = 1

_MAX_TEXT = 4000  # user free-text cap (defensive; the UI also limits it)

# Scrub the VALUE of any dict key that looks like a hardware identifier.
_SCRUB_KEY = re.compile(r"serial|uuid|\bmac\b|mac_?addr|hostname|host_name", re.I)
_HOME_PATH = re.compile(r"/home/[^/\s:\"']+")
# Identifiers that can appear inside free text (log lines, dmesg/journal output).
_MAC = re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
# Serial numbers leak in DMI/dmesg dumps ("board_serial: ...", "Serial Number: ...").
# Keep the label for context, drop the value.
_SERIAL_LABELED = re.compile(
    r"((?:board|product|chassis|system|baseboard)?_?serial(?:\s*number)?)(\s*[:=]\s*)(\S+)",
    re.I,
)
# A standalone long alphanumeric run that mixes letters AND digits (typical serial
# shape). Pure words ('steamdeck') and pure numbers (timestamps) are left alone.
_SERIAL_RUN = re.compile(
    r"\b(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{8,}\b"
)


def redact_text(s, *, home: str | None = None, hostname: str | None = None):
    """Scrub PII from a string: home paths, an explicit hostname, MAC/UUID and
    serial-like values that show up inside log or kernel output. Never touches a
    bare username token (that would nuke 'Steam Deck' when the user is 'deck')."""
    if not isinstance(s, str):
        return s
    s = _HOME_PATH.sub("~", s)
    if home:
        s = s.replace(home.rstrip("/"), "~")
    if hostname and len(hostname) >= 3:
        s = re.sub(rf"\b{re.escape(hostname)}\b", "HOST", s)
    s = _MAC.sub("[mac]", s)
    s = _UUID.sub("[uuid]", s)
    s = _SERIAL_LABELED.sub(lambda m: f"{m.group(1)}{m.group(2)}[serial]", s)
    s = _SERIAL_RUN.sub("[serial]", s)
    return s


def redact_obj(obj, *, home: str | None = None, hostname: str | None = None):
    """Recursively redact a JSON-ish structure: scrub serial-like key values and
    run redact_text on every string. Idempotent."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SCRUB_KEY.search(k) and isinstance(v, (str, int, float)):
                out[k] = "[redacted]"
            else:
                out[k] = redact_obj(v, home=home, hostname=hostname)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact_obj(x, home=home, hostname=hostname) for x in obj]
    return redact_text(obj, home=home, hostname=hostname)


def _tail_file(path: str, n: int) -> str:
    """Last ~n bytes of a file, decoded leniently, with a partial leading line
    dropped so the excerpt starts on a clean line."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        start = max(0, size - n)
        f.seek(start)
        raw = f.read()
    txt = raw.decode("utf-8", "replace")
    if start > 0:
        nl = txt.find("\n")
        if nl != -1:
            txt = txt[nl + 1:]
    return txt


def tail_logs(
    log_dir: str,
    *,
    max_files: int = 3,
    max_bytes: int = 200_000,
    home: str | None = None,
    hostname: str | None = None,
) -> list[dict]:
    """The tail of the newest *.log files in log_dir (newest first), redacted and
    capped to a shared byte budget. Never raises → returns [] on any problem."""
    try:
        files = sorted(
            glob.glob(os.path.join(log_dir, "*.log")),
            key=os.path.getmtime,
            reverse=True,
        )
    except Exception:  # noqa: BLE001
        return []
    out: list[dict] = []
    budget = max_bytes
    for path in files[:max_files]:
        if budget <= 0:
            break
        try:
            data = _tail_file(path, budget)
        except Exception:  # noqa: BLE001
            continue
        out.append({
            "name": os.path.basename(path),
            "text": redact_text(data, home=home, hostname=hostname),
        })
        budget -= len(data)
    return out


# Kernel-side evidence: firmware/hardware write rejections (TDP, fan curves) land
# in dmesg/journal, NOT the plugin's own log. Captured via an injected runner so
# this stays testable without spawning processes.
_KERNEL_CMDS = {
    "dmesg": ["/usr/bin/dmesg", "--ctime", "--level=err,warn"],
    "journal": ["/usr/bin/journalctl", "-b", "-u", "plugin_loader", "-n", "400", "--no-pager"],
}


# The controller daemon (HHD on Bazzite, InputPlumber on SteamOS) owns the gamepad
# and its own resume/re-grab. Controller failures land in ITS journal, not the
# plugin log — so a controller report should carry it. Keyed by the manager string
# reported by controllers.detect (values, not imported, to keep this standalone).
_CONTROLLER_UNITS = {"hhd": "hhd.service", "inputplumber": "inputplumber.service"}


def controller_daemon_cmds(manager: str | None) -> dict:
    """Extra kernel_logs command for the active controller daemon's journal, or an
    empty dict when no daemon runs the controller (nothing to capture)."""
    unit = _CONTROLLER_UNITS.get(manager or "")
    if not unit:
        return {}
    return {"controller": ["/usr/bin/journalctl", "-b", "-u", unit, "-n", "300", "--no-pager"]}


def kernel_logs(
    run,
    *,
    cap: int = 40_000,
    extra: dict | None = None,
    home: str | None = None,
    hostname: str | None = None,
) -> dict:
    """Tail of dmesg (errors/warnings) + the plugin_loader journal, plus any `extra`
    {key: cmd} commands (e.g. the controller daemon journal), via run(cmd)->str|None.
    Redacted and size-capped. Never raises."""
    out = {}
    for key, cmd in {**_KERNEL_CMDS, **(extra or {})}.items():
        try:
            text = run(cmd)
        except Exception:  # noqa: BLE001
            text = None
        out[key] = redact_text(text[-cap:], home=home, hostname=hostname) if text else None
    return out


# Raw sysfs surfaces that decide device support. A listing (node/dir NAMES, plus a
# couple of tiny label values) so a triager can tell "node exists but capability
# reads false → probe bug" from "node absent → truly unsupported". Bounded to keep
# the bundle small and to never sweep /sys recursively.
_SNAP_MAX_CHIPS = 32
_SNAP_MAX_NAMES = 128
_SNAP_MAX_MODULES = 512
_SNAP_CAP = 60_000
_HWMON_PATTERNS = ("pwm*", "fan*_input", "temp*_label")


def _glob(root: str, pattern: str) -> list[str]:
    try:
        return glob.glob(os.path.join(root, pattern))
    except Exception:  # noqa: BLE001
        return []


def _listdir(path: str) -> list[str]:
    try:
        return os.listdir(path)
    except OSError:
        return []


def _hwmon_nodes(chip_dir: str) -> list[str]:
    names: set[str] = set()
    for pat in _HWMON_PATTERNS:
        for p in _glob(chip_dir, pat):
            names.add(os.path.basename(p))
    return sorted(names)[:_SNAP_MAX_NAMES]


def _snap_hwmon(root: str) -> list[dict]:
    out: list[dict] = []
    for chip in sorted(_glob(root, "sys/class/hwmon/hwmon*"))[:_SNAP_MAX_CHIPS]:
        try:
            out.append({"name": read_str(os.path.join(chip, "name")), "nodes": _hwmon_nodes(chip)})
        except Exception:  # noqa: BLE001
            continue
    return out


def _snap_dir_listing(root: str, pattern: str, sub: str = "") -> dict:
    """Map each matched dir's basename to a sorted listing of the names inside it
    (optionally a `sub` child dir). Diagnoses WMI attributes / power_supply nodes."""
    out: dict = {}
    for d in sorted(_glob(root, pattern))[:_SNAP_MAX_CHIPS]:
        try:
            out[os.path.basename(d)] = sorted(_listdir(os.path.join(d, sub) if sub else d))[:_SNAP_MAX_NAMES]
        except Exception:  # noqa: BLE001
            out[os.path.basename(d)] = []
    return out


def _snap_platform_profile(root: str) -> dict:
    """The performance-mode surface: the ACPI single-file interface plus the class
    interface (Legion's lenovo-wmi-gamezone exposes its firmware modes here). Tells a
    triager which modes a device offers and which is active."""
    out: dict = {"acpi": {}, "class": {}}
    base = os.path.join(root, "sys/firmware/acpi")
    cur = read_str(os.path.join(base, "platform_profile"))
    choices = read_str(os.path.join(base, "platform_profile_choices"))
    if cur is not None:
        out["acpi"]["current"] = cur
    if choices is not None:
        out["acpi"]["choices"] = choices
    for d in sorted(_glob(root, "sys/class/platform-profile/*"))[:_SNAP_MAX_CHIPS]:
        try:
            out["class"][os.path.basename(d)] = {
                "name": read_str(os.path.join(d, "name")),
                "profile": read_str(os.path.join(d, "profile")),
                "choices": read_str(os.path.join(d, "choices")),
            }
        except Exception:  # noqa: BLE001
            continue
    return out


_LEGACY_PPT = ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_fppt")


def _snap_asus_ppt(root: str) -> dict:
    """Both ASUS PL1 interfaces WITH their live values: asus-armoury (firmware-attributes,
    current/min/max triplet) and the legacy asus-nb-wmi (direct value files). Values, not
    just names — a triager needs to see a bogus firmware ceiling (e.g. 150) and whether
    the second interface exists and what it holds vs the first."""
    out: dict = {"asus_armoury": {}, "asus_nb_wmi": {}}
    fw = os.path.join(root, "sys/class/firmware-attributes/asus-armoury/attributes")
    for a in ("ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"):
        d = os.path.join(fw, a)
        if os.path.isdir(d):
            out["asus_armoury"][a] = {
                "current": read_str(os.path.join(d, "current_value")),
                "min": read_str(os.path.join(d, "min_value")),
                "max": read_str(os.path.join(d, "max_value")),
            }
    legacy = os.path.join(root, "sys/devices/platform/asus-nb-wmi")
    for a in _LEGACY_PPT:
        v = read_str(os.path.join(legacy, a))
        if v is not None:
            out["asus_nb_wmi"][a] = v
    return out


def _snap_acpi(root: str) -> dict:
    path = os.path.join(root, "proc/acpi/call")
    try:
        present = os.path.exists(path)
        writable = bool(present and os.access(path, os.W_OK))
    except Exception:  # noqa: BLE001
        present, writable = False, False
    return {"call_present": present, "call_writable": writable}


def _snap_modules(root: str) -> list[str]:
    """Loaded kernel module names from /proc/modules (bounded line read, never
    lsmod). Makes ALIB-vs-ryzenadj viability obvious (acpi_call present?)."""
    names: list[str] = []
    try:
        with open(os.path.join(root, "proc/modules")) as f:
            for line in f:
                name = line.split(" ", 1)[0].strip()
                if name:
                    names.append(name)
                if len(names) >= _SNAP_MAX_MODULES:
                    break
    except OSError:
        return []
    return sorted(names)


def _within(obj, cap: int) -> bool:
    try:
        return len(json.dumps(obj, default=str)) <= cap
    except Exception:  # noqa: BLE001
        return True


def sysfs_snapshot(
    root: str = "/",
    *,
    cap: int = _SNAP_CAP,
    home: str | None = None,
    hostname: str | None = None,
) -> dict:
    """Redacted, size-capped listing of the sysfs surfaces that decide fan/temp,
    vendor-WMI TDP, charge-limit/battery, and ACPI-call support. Listing only —
    bounded-depth globs, NEVER a recursive walk of /sys. Never raises: any missing
    or unreadable path records an absent/empty marker."""
    snap: dict = {"hwmon": [], "firmware_attributes": {}, "power_supply": {},
                  "platform_profile": {"acpi": {}, "class": {}}, "acpi": {}, "modules": [],
                  "asus_ppt": {"asus_armoury": {}, "asus_nb_wmi": {}}}
    try:
        snap["hwmon"] = _snap_hwmon(root)
    except Exception:  # noqa: BLE001
        pass
    try:
        snap["firmware_attributes"] = _snap_dir_listing(
            root, "sys/class/firmware-attributes/*", "attributes"
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        snap["power_supply"] = _snap_dir_listing(root, "sys/class/power_supply/*")
    except Exception:  # noqa: BLE001
        pass
    try:
        snap["platform_profile"] = _snap_platform_profile(root)
    except Exception:  # noqa: BLE001
        pass
    try:
        snap["asus_ppt"] = _snap_asus_ppt(root)
    except Exception:  # noqa: BLE001
        pass
    try:
        snap["acpi"] = _snap_acpi(root)
    except Exception:  # noqa: BLE001
        pass
    try:
        snap["modules"] = _snap_modules(root)
    except Exception:  # noqa: BLE001
        pass
    # Backstop the count caps: if the listing is still oversized, drop the heaviest
    # sections and flag it honestly rather than shipping an unbounded blob.
    if not _within(snap, cap):
        snap["truncated"] = True
        for key in ("modules", "hwmon", "power_supply", "firmware_attributes"):
            if _within(snap, cap):
                break
            snap[key] = [] if isinstance(snap[key], list) else {}
    return redact_obj(snap, home=home, hostname=hostname)


def capabilities_from(states: dict) -> dict:
    """Distil the per-subsystem detected backends + supported flags from the live
    state dicts. This is the single most useful section for triage: many reports
    are 'X doesn't work' when X simply has no write path on that device."""
    tdp = states.get("tdp") or {}
    fan = states.get("fan_curve") or {}
    batt = (states.get("battery") or {}).get("charge_limit") or {}
    gpu = states.get("gpu") or {}
    color = states.get("color") or {}
    ctl = states.get("controller") or {}
    launch = states.get("launch") or {}
    ltools = launch.get("tools") or {}
    running = (launch.get("frontend") or {}).get("runningGame")
    running = running if isinstance(running, dict) else {}
    return {
        "tdp_backend": tdp.get("backend"),
        "tdp_supported": bool(tdp.get("supported")),
        "fan_source": fan.get("source"),
        "fan_supported": bool(fan.get("supported")),
        # Experimental EC fan control (Legion Go S): whether the device offers the
        # unofficial channel and whether the user opted in. Key for fan reports —
        # "modes do nothing" reads very differently with this off vs on.
        "fan_experimental_available": bool(fan.get("experimental_available")),
        "fan_experimental_enabled": bool(fan.get("experimental_enabled")),
        "charge_limit_supported": bool(batt.get("supported")),
        "charge_limit_adjustable": bool(batt.get("adjustable")),
        "gpu_clock_supported": bool(gpu.get("supported")),
        "color_supported": bool(color.get("supported")),
        "controller_manager": ctl.get("manager"),
        "controller_kind": ctl.get("kind"),
        # Launch options: tools detected + (running game) malformed string / Proton resolved.
        "launch_lsfg": bool(ltools.get("lsfg")),
        "launch_mangohud": bool(ltools.get("mangohud")),
        "launch_distro": ltools.get("distro"),
        "launch_running_compat": running.get("compatTool"),
        "launch_running_proton_found": running.get("protonFound"),
        "launch_running_malformed": running.get("malformed"),
    }


def build_bundle(
    *,
    app: str,
    categories,
    text,
    environment: dict,
    capabilities: dict,
    state: dict,
    stores: dict,
    logs: list,
    kernel: dict | None = None,
    sysfs: dict | None = None,
    home: str | None = None,
    hostname: str | None = None,
) -> dict:
    """Assemble the final bundle from already-fetched pieces and redact the whole
    thing again (logs are pre-redacted; this catches the rest)."""
    bundle = {
        "schema": SCHEMA,
        "app": app,
        "categories": list(categories or []),
        "text": (text or "")[:_MAX_TEXT],
        "environment": environment or {},
        "capabilities": capabilities or {},
        "state": state or {},
        "stores": stores or {},
        "logs": logs or [],
        "kernel": kernel or {},
        "sysfs": sysfs or {},
    }
    return redact_obj(bundle, home=home, hostname=hostname)
