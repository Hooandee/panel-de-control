"""Inventory of the devices attached to the machine, read from sysfs only.

Answers "what is plugged in" for a report (docks, external coolers, controllers,
eGPUs) without running lsusb/lspci. Serial numbers, MAC addresses (input `uniq`,
`phys`) and user-given Bluetooth names are never read.
"""
from __future__ import annotations

import glob
import os

from sysfs import read_str

_MAX_PER_BUS = 64


def _attrs(path: str, names: tuple[str, ...]) -> dict:
    out = {}
    for name in names:
        value = read_str(os.path.join(path, name))
        if value is not None and value.strip():
            out[name] = value.strip()
    return out


def _driver(path: str) -> str | None:
    link = os.path.join(path, "driver")
    try:
        return os.path.basename(os.readlink(link)) if os.path.islink(link) else None
    except OSError:
        return None


def _entries(root: str, pattern: str, required: str | None = None) -> list[str]:
    paths = sorted(glob.glob(os.path.join(root, pattern)))
    if required:
        paths = [path for path in paths if os.path.exists(os.path.join(path, required))]
    return paths[:_MAX_PER_BUS]


def _usb(root: str) -> list[dict]:
    devices = []
    for path in _entries(root, "sys/bus/usb/devices/*", required="idVendor"):
        device = {"bus_path": os.path.basename(path)}
        device.update(_attrs(path, ("idVendor", "idProduct", "manufacturer", "product",
                                    "bDeviceClass", "speed")))
        interfaces = []
        for interface in sorted(glob.glob(path + ":*")):
            entry = _attrs(interface, ("bInterfaceClass",))
            driver = _driver(interface)
            if driver:
                entry["driver"] = driver
            if entry:
                interfaces.append(entry)
        if interfaces:
            device["interfaces"] = interfaces
        devices.append(device)
    return devices


def _hid(root: str) -> list[dict]:
    devices = []
    for path in _entries(root, "sys/bus/hid/devices/*"):
        device = {"id": os.path.basename(path)}
        driver = _driver(path)
        if driver:
            device["driver"] = driver
        devices.append(device)
    return devices


def _input(root: str) -> list[dict]:
    devices = []
    for path in _entries(root, "sys/class/input/input*"):
        device = _attrs(path, ("name",))
        device.update({f"id_{key}": value for key, value in
                       _attrs(os.path.join(path, "id"),
                              ("bustype", "vendor", "product")).items()})
        if device:
            devices.append(device)
    return devices


def _pci(root: str) -> list[dict]:
    devices = []
    for path in _entries(root, "sys/bus/pci/devices/*"):
        device = {"address": os.path.basename(path)}
        device.update(_attrs(path, ("vendor", "device", "class")))
        driver = _driver(path)
        if driver:
            device["driver"] = driver
        devices.append(device)
    return devices


def _thunderbolt(root: str) -> list[dict]:
    devices = []
    for path in _entries(root, "sys/bus/thunderbolt/devices/*"):
        device = _attrs(path, ("vendor_name", "device_name"))
        if device:
            devices.append({"id": os.path.basename(path), **device})
    return devices


def _bluetooth_adapters(root: str) -> list[str]:
    return [os.path.basename(path) for path in _entries(root, "sys/class/bluetooth/hci*")]


def snapshot(root: str = "/") -> dict:
    """Bounded per-bus listing. Never raises: an unreadable bus is an empty list."""
    out = {}
    for key, read in (("usb", _usb), ("hid", _hid), ("input", _input), ("pci", _pci),
                      ("thunderbolt", _thunderbolt), ("bluetooth_adapters", _bluetooth_adapters)):
        try:
            out[key] = read(root)
        except Exception:  # noqa: BLE001
            out[key] = []
    return out
