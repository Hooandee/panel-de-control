"""Inventory of the devices attached to the machine, read from sysfs only.

Answers "what is plugged in" for a report (docks, external coolers, controllers,
eGPUs) without running lsusb/lspci. Serial numbers, MAC addresses (input `uniq`,
`phys`) and Bluetooth input names, which carry the user's name for the device,
are never kept.
"""
from __future__ import annotations

import glob
import os

from sysfs import read_str

_MAX_PER_BUS = 64
_BUS_BLUETOOTH = "0005"


def _attrs(path: str, names: tuple[str, ...]) -> dict:
    out = {}
    for name in names:
        value = read_str(os.path.join(path, name))
        if value is not None and value.strip():
            out[name] = value.strip()
    return out


def _hex_attrs(path: str, names: tuple[str, ...]) -> dict:
    # Without the 0x prefix: "0x030000" has the shape the report serial scrubber removes.
    return {name: value.removeprefix("0x") for name, value in _attrs(path, names).items()}


def _driver(path: str) -> dict:
    link = os.path.join(path, "driver")
    try:
        return {"driver": os.path.basename(os.readlink(link))} if os.path.islink(link) else {}
    except OSError:
        return {}


def _usb(path: str) -> dict:
    name = os.path.basename(path)
    interface_glob = f"{name[3:]}-0:*" if name.startswith("usb") else f"{name}:*"
    interfaces = [
        {**_attrs(interface, ("bInterfaceClass",)), **_driver(interface)}
        for interface in sorted(glob.glob(os.path.join(os.path.dirname(path), interface_glob)))
    ]
    device = {"bus_path": name,
              **_attrs(path, ("idVendor", "idProduct", "manufacturer", "product",
                              "bDeviceClass", "speed"))}
    interfaces = [interface for interface in interfaces if interface]
    return {**device, "interfaces": interfaces} if interfaces else device


def _hid(path: str) -> dict:
    return {"id": os.path.basename(path), **_driver(path)}


def _input(path: str) -> dict:
    ids = {f"id_{key}": value for key, value in
           _attrs(os.path.join(path, "id"), ("bustype", "vendor", "product")).items()}
    name = _attrs(path, ("name",))
    if ids.get("id_bustype") == _BUS_BLUETOOTH or name.get("name", "").endswith("(AVRCP)"):
        return ids
    return {**name, **ids}


def _pci(path: str) -> dict:
    return {"address": os.path.basename(path),
            **_hex_attrs(path, ("vendor", "device", "class")), **_driver(path)}


def _thunderbolt(path: str) -> dict:
    names = _attrs(path, ("vendor_name", "device_name"))
    return {"id": os.path.basename(path), **names} if names else {}


def _bluetooth_adapter(path: str) -> dict:
    return {"id": os.path.basename(path)}


_BUSES = (
    ("usb", "sys/bus/usb/devices/*", lambda path: os.path.exists(os.path.join(path, "idVendor")), _usb),
    ("hid", "sys/bus/hid/devices/*", None, _hid),
    ("input", "sys/class/input/input*", None, _input),
    ("pci", "sys/bus/pci/devices/*", None, _pci),
    ("thunderbolt", "sys/bus/thunderbolt/devices/*", None, _thunderbolt),
    ("bluetooth_adapters", "sys/class/bluetooth/hci*", lambda path: ":" not in os.path.basename(path),
     _bluetooth_adapter),
)


def snapshot(root: str = "/") -> dict:
    """Bounded per-bus listing; `truncated` holds the real count of any bus over the
    cap. Never raises: an unreadable bus is an empty list."""
    out: dict = {}
    truncated = {}
    for key, pattern, keep, read in _BUSES:
        try:
            paths = sorted(glob.glob(os.path.join(root, pattern)))
            if keep:
                paths = [path for path in paths if keep(path)]
            out[key] = [device for device in map(read, paths[:_MAX_PER_BUS]) if device]
            if len(paths) > _MAX_PER_BUS:
                truncated[key] = len(paths)
        except Exception:  # noqa: BLE001
            out[key] = []
    if truncated:
        out["truncated"] = truncated
    return out
