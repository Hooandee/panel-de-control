"""Hardware fingerprint of the reporting machine.

Identity plus the raw hardware surfaces Panel reads or writes, keyed by their path
relative to `/` so a real report can be replayed as a sysfs fixture tree. Read-only
and allowlisted (never a recursive walk of /sys), bounded per file, by a deadline and
in total size, and redacted. Never raises: a failing section lands in `errors`.
"""
from __future__ import annotations

import glob
import json
import os
import re
import stat
import time

from osinfo import _parse_os_release
from pdc_report.collector import redact_text

SCHEMA = 1
MAX_BYTES = 256 * 1024
DEADLINE_S = 5.0
_READ_BYTES = 4096
_IDENTITY_BYTES = 256
_PROC_READ_BYTES = 64 * 1024
_MAX_FILES = 96
_MAX_INPUT_DEVICES = 64
_MAX_PLATFORM_DEVICES = 64

_DMI_FIELDS = (
    "sys_vendor", "product_name", "product_version", "product_family", "product_sku",
    "board_vendor", "board_name", "board_version",
    "chassis_vendor", "chassis_type", "chassis_version",
    "bios_vendor", "bios_version", "bios_date", "bios_release", "ec_firmware_release",
)

# (section, directory glob, file globs inside each directory, max directories)
_SURFACES = (
    ("hwmon", "sys/class/hwmon/hwmon*",
     ("name", "pwm*", "fan*_input", "fan*_label", "fan*_min", "fan*_max", "fan*_target",
      "temp*_input", "temp*_label", "temp*_max", "temp*_crit",
      "power*_label", "power*_cap*", "power*_average", "power*_input"), 32),
    ("power_supply", "sys/class/power_supply/*",
     ("type", "scope", "online", "present", "status", "capacity", "capacity_level",
      "charge_control_*", "charge_behaviour", "charge_type", "charge_types", "technology",
      "manufacturer", "model_name", "cycle_count", "energy_*", "charge_full*", "charge_now",
      "voltage_*", "current_now", "power_now", "usb_type"), 16),
    ("leds", "sys/class/leds/*",
     ("max_brightness", "brightness", "multi_index", "multi_intensity"), 64),
    ("drm", "sys/class/drm/card*",
     ("status", "enabled", "dpms", "modes", "device/vendor", "device/device",
      "device/subsystem_vendor", "device/subsystem_device", "device/revision"), 32),
    ("platform_profile", "sys/class/platform-profile/*", ("name", "profile", "choices"), 8),
    ("acpi", "sys/firmware/acpi", ("platform_profile", "platform_profile_choices"), 1),
    ("devicetree", "sys/firmware/devicetree/base", ("model", "compatible"), 1),
    # Last: a vendor with hundreds of attributes must not spend the others' deadline.
    ("firmware_attributes", "sys/class/firmware-attributes/*/attributes/*",
     ("type", "display_name", "current_value", "default_value", "min_value", "max_value",
      "scalar_increment", "possible_values"), 256),
)

_VENDOR_PLATFORM = re.compile(
    r"asus|lenovo|legion|ideapad|thinkpad|msi|oxp|onexplayer|ayaneo|ayn|gpd|zotac|acer"
    r"|hp-|dell|framework|steamdeck|jupiter|galileo|valve|vlv|wmi",
    re.I,
)
_PRIVATE_WORDS = ("serial", "uuid", "guid", "password", "passwd", "asset", "owner",
                  "macaddr", "mac_addr", "ssid", "secret", "edid")
_PRIVATE_TOKENS = frozenset({"tag", "mac", "pin", "tracking", "born"})
_NAME_TOKENS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
# Read only to scrub their values wherever a vendor repeats them; never reported.
_SECRET_FILES = ("sys/class/dmi/id/product_serial", "sys/class/dmi/id/board_serial",
                 "sys/class/dmi/id/chassis_serial", "sys/class/dmi/id/product_uuid",
                 "sys/class/dmi/id/board_asset_tag", "sys/class/dmi/id/chassis_asset_tag",
                 "sys/class/power_supply/*/serial_number")
_PLACEHOLDER = re.compile(r"default|o\.e\.m|none|unknown|not |n/a|^[0x\s.-]*$|^123456", re.I)
_PERIPHERAL_PREFIXES = ("hid-", "ps-controller-battery-", "wacom_battery_")
_PERIPHERAL_FILES = ("type", "scope", "present")
_CPU_FIELDS = ("vendor_id", "model name", "cpu family", "model", "stepping", "microcode",
               "CPU implementer", "CPU part", "Hardware")
_OS_RELEASE_FIELDS = ("ID", "ID_LIKE", "NAME", "PRETTY_NAME", "VERSION_ID", "BUILD_ID",
                      "VARIANT_ID", "IMAGE_VERSION")
_BUS_BLUETOOTH = "0005"
_STOCK_USERS = frozenset({"deck", "root", "user", "steam", "gamer", "admin", "games"})
_MAC = re.compile(r"\b(?:[0-9a-fA-F]{2}[:_-]){5}[0-9a-fA-F]{2}\b")
_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_IPV6 = re.compile(r"(?<![\w:])[0-9a-fA-F]{0,4}(?::[0-9a-fA-F]{0,4}){2,7}(?![\w:])")


def _private(name: str) -> bool:
    lower = name.lower()
    tokens = {token.lower() for token in _NAME_TOKENS.findall(name)}
    return any(word in lower for word in _PRIVATE_WORDS) or bool(_PRIVATE_TOKENS & tokens)


def _ipv6(match: re.Match) -> str:
    text = match.group(0)
    return "[ip]" if text.count("::") == 1 or text.count(":") == 7 else text


class _Redactor:
    """Hardware values (`free_text=False`) only lose identifiers: scrubbing a stock
    hostname, a short username or a dotted version there would mangle the very
    strings that identify the machine ("bazzite", "max-power", "1.0.0.4")."""

    def __init__(self, home, hostname, secrets=(), *, free_text: bool = True):
        self._home = home
        self._hostname = hostname if free_text else None
        self._free_text = free_text
        self._secrets = sorted(secrets, key=len, reverse=True)
        user = os.path.basename((home or "").rstrip("/"))
        self._user = (re.compile(rf"\b{re.escape(user)}\b", re.I)
                      if free_text and len(user) >= 3 and user.lower() not in _STOCK_USERS
                      else None)

    def text(self, value: str) -> str:
        for secret in self._secrets:
            value = value.replace(secret, "[serial]")
        value = redact_text(value, home=self._home, hostname=self._hostname,
                            keep_serial_runs=True)
        if self._free_text:
            value = _IPV6.sub(_ipv6, _IPV4.sub("[ip]", value))
        return self._user.sub("[user]", value) if self._user else value

    def obj(self, value):
        if isinstance(value, dict):
            out: dict = {}
            for key, item in value.items():
                key = str(key)
                if _private(os.path.basename(key)):
                    continue
                key = base = _MAC.sub("[mac]", key)
                copy = 1
                while key in out:
                    copy += 1
                    key = f"{base}#{copy}"
                out[key] = self.obj(item)
            return out
        if isinstance(value, (list, tuple, set, frozenset)):
            return [self.obj(item) for item in value]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return self.text(str(value))


class _Reader:
    """Bounded sysfs reads that stop once the deadline passes, so a slow EC or ACPI
    attribute can only cost the remaining budget."""

    def __init__(self, root: str, deadline_s: float, clock):
        self.root = root
        self._clock = clock
        self._end = clock() + deadline_s
        self.expired = False

    def rel(self, path: str) -> str:
        return os.path.relpath(path, self.root)

    def read(self, path: str, limit: int = _READ_BYTES) -> str | None:
        if self.expired or self._clock() >= self._end:
            self.expired = True
            return None
        try:
            mode = os.stat(path).st_mode
            if not stat.S_ISREG(mode) or not mode & 0o444:
                return None
            with open(path, "rb") as f:
                data = f.read(limit)
        except OSError:
            return None
        return data.replace(b"\0", b" ").decode("utf-8", "replace").strip()

    def glob(self, pattern: str) -> list[str]:
        return sorted(glob.glob(os.path.join(self.root, pattern)))


def _dmi(reader: _Reader) -> dict:
    base = os.path.join(reader.root, "sys/class/dmi/id")
    values = {name: reader.read(os.path.join(base, name), _IDENTITY_BYTES)
              for name in _DMI_FIELDS}
    return {name: value for name, value in values.items() if value is not None}


def _surface(reader: _Reader, directory_glob: str, files: tuple, max_dirs: int) -> dict:
    out: dict = {}
    for directory in reader.glob(directory_glob)[:max_dirs]:
        if _private(os.path.basename(directory)):
            continue
        # Reading a runtime-suspended device (a hybrid laptop's dGPU), a peripheral's
        # battery or a disk's drivetemp would wake it or block on the device.
        peripheral = os.path.basename(directory).startswith(_PERIPHERAL_PREFIXES)
        wanted = files
        if reader.read(os.path.join(directory, "device/power/runtime_status")) == "suspended":
            wanted = ("name",)
        elif peripheral:
            wanted = _PERIPHERAL_FILES
        elif reader.read(os.path.join(directory, "name")) == "drivetemp":
            wanted = ("name",)
        paths = sorted({path for pattern in wanted
                        for path in glob.glob(os.path.join(directory, pattern))})
        for path in paths[:_MAX_FILES]:
            name = os.path.basename(path)
            if _private(name):
                continue
            value = reader.read(path)
            if value is not None:
                out[reader.rel(path)] = value
    return out


def _cpu(reader: _Reader) -> dict:
    out: dict = {}
    text = reader.read(os.path.join(reader.root, "proc/cpuinfo"), _PROC_READ_BYTES) or ""
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key = key.strip()
        if key in _CPU_FIELDS and key not in out:
            out[key] = value.strip()[:_IDENTITY_BYTES]
    out["logical_cpus"] = len(reader.glob("sys/devices/system/cpu/cpu[0-9]*"))
    return out


def _link_name(path: str) -> str | None:
    try:
        return os.path.basename(os.readlink(path)) if os.path.islink(path) else None
    except OSError:
        return None


def _gpus(reader: _Reader) -> list[dict]:
    out = []
    for card in reader.glob("sys/class/drm/card[0-9]*"):
        if "-" in os.path.basename(card):
            continue
        device = os.path.join(card, "device")
        out.append({
            "card": os.path.basename(card),
            "driver": _link_name(os.path.join(device, "driver")),
            "bus_id": os.path.basename(os.path.realpath(device)),
            "vendor": reader.read(os.path.join(device, "vendor")),
            "device": reader.read(os.path.join(device, "device")),
            "product_name": reader.read(os.path.join(device, "product_name")),
        })
    return out


def _system(reader: _Reader) -> dict:
    release = _parse_os_release(reader.root)
    return {
        "kernel": reader.read(os.path.join(reader.root, "proc/sys/kernel/osrelease")),
        "distro": {key: release[key] for key in _OS_RELEASE_FIELDS if key in release},
    }


def _platform_devices(reader: _Reader) -> list[dict]:
    out = []
    for device in reader.glob("sys/devices/platform/*"):
        name = os.path.basename(device)
        if not _VENDOR_PLATFORM.search(name) or not os.path.isdir(device):
            continue
        attributes = sorted(
            entry for entry in os.listdir(device)
            if entry not in ("uevent", "modalias", "driver_override")
            and os.path.isfile(os.path.join(device, entry))
        )
        out.append({"name": name, "driver": _link_name(os.path.join(device, "driver")),
                    "attributes": attributes[:_MAX_FILES]})
    return out[:_MAX_PLATFORM_DEVICES]


def _input_devices(reader: _Reader) -> list[dict]:
    text = reader.read(os.path.join(reader.root, "proc/bus/input/devices"), _PROC_READ_BYTES)
    out = []
    for block in (text or "").split("\n\n"):
        entry: dict = {}
        for line in block.splitlines():
            kind, _, rest = line.partition(": ")
            if kind == "I":
                entry.update({key.lower(): value for key, _, value in
                              (field.partition("=") for field in rest.split())})
            elif kind == "N":
                entry["name"] = rest.partition("=")[2].strip('"')
            elif kind == "H":
                entry["handlers"] = rest.partition("=")[2].strip()
        if not entry:
            continue
        if entry.get("bus") == _BUS_BLUETOOTH:
            entry.pop("name", None)
        out.append(entry)
    return out[:_MAX_INPUT_DEVICES]


def _size(value) -> int:
    return len(json.dumps(value, default=str))


def _fit(fingerprint: dict, max_bytes: int) -> None:
    """Drop the heaviest surfaces/lists until the fingerprint fits, naming each one."""
    if _size(fingerprint) <= max_bytes:
        return
    candidates = [("surfaces", name) for name in fingerprint.get("surfaces", {})]
    candidates += [(key,) for key in ("input_devices", "platform_devices", "panel")
                   if key in fingerprint]

    def weight(path):
        node = fingerprint
        for key in path:
            node = node[key]
        return _size(node)

    for path in sorted(candidates, key=weight, reverse=True):
        parent = fingerprint if len(path) == 1 else fingerprint[path[0]]
        parent.pop(path[-1], None)
        fingerprint["truncated"].append("/".join(path))
        if _size(fingerprint) <= max_bytes:
            return
    for key in [key for key in fingerprint if key not in ("schema", "errors", "truncated")]:
        del fingerprint[key]
    fingerprint["truncated"] = ["oversize"]


def _secrets(reader: _Reader) -> set[str]:
    values = (reader.read(path, _IDENTITY_BYTES)
              for pattern in _SECRET_FILES for path in reader.glob(pattern))
    return {value for value in values
            if value and len(value) >= 5 and not _PLACEHOLDER.search(value)}


def failed(error: str, *, panel=None, home: str | None = None,
           hostname: str | None = None, max_bytes: int = MAX_BYTES) -> dict:
    """The fingerprint to ship when the read itself did not finish."""
    fingerprint = {"schema": SCHEMA, "errors": {"collect": error}, "truncated": [],
                   "panel": _Redactor(home, hostname).obj(panel)}
    _fit(fingerprint, max_bytes)
    return fingerprint


def collect(
    root: str = "/",
    *,
    panel: dict | None = None,
    home: str | None = None,
    hostname: str | None = None,
    deadline_s: float = DEADLINE_S,
    max_bytes: int = MAX_BYTES,
    clock=time.monotonic,
) -> dict:
    """Read the fingerprint. `panel` carries what only the running plugin knows
    (versions, chosen device profile, TDP method and recent writes)."""
    reader = _Reader(root, deadline_s, clock)
    errors: dict = {}
    try:
        secrets = _secrets(reader)
    except Exception as error:  # noqa: BLE001
        secrets = set()
        errors["secrets"] = type(error).__name__
    hardware = _Redactor(home, hostname, secrets, free_text=False)
    free_text = _Redactor(home, hostname, secrets)
    fingerprint: dict = {"schema": SCHEMA, "errors": errors, "truncated": []}
    sections = (
        ("dmi", _dmi, hardware), ("cpu", _cpu, hardware), ("gpus", _gpus, hardware),
        ("system", _system, hardware), ("platform_devices", _platform_devices, hardware),
        ("input_devices", _input_devices, free_text),
    )
    for name, read, redactor in sections:
        try:
            fingerprint[name] = redactor.obj(read(reader))
        except Exception as error:  # noqa: BLE001
            errors[name] = type(error).__name__
    surfaces: dict = {}
    for name, directory_glob, files, max_dirs in _SURFACES:
        try:
            surfaces[name] = hardware.obj(_surface(reader, directory_glob, files, max_dirs))
        except Exception as error:  # noqa: BLE001
            errors[f"surfaces/{name}"] = type(error).__name__
    fingerprint["surfaces"] = surfaces
    if panel is not None:
        try:
            fingerprint["panel"] = free_text.obj(panel)
        except Exception as error:  # noqa: BLE001
            errors["panel"] = type(error).__name__
    if reader.expired:
        fingerprint["truncated"].append("deadline")
    _fit(fingerprint, max_bytes)
    return fingerprint
