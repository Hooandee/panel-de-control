"""Find the panel's CH340 bridge and anything else holding it open."""

import os
from dataclasses import dataclass
from pathlib import Path

_VENDOR = "1a86"
_PRODUCT = "7523"
# USB root ports the official app treats as able to feed the panel's full current (Steam
# Machine). Anything else, hubs included, gets the weak-supply brightness ceiling.
STRONG_SUPPLY_PORTS = frozenset({"7-1", "5-1", "1-2"})
_BOOT_ID = Path("/proc/sys/kernel/random/boot_id")


@dataclass(frozen=True)
class PanelPort:
    dev: str
    bus_port: str
    strong_supply: bool
    # Bus and device number change on every plug-in or power loss, when the panel restarts on its
    # firmware animation instead of the last GIF. A cold boot can hand out the same numbers again,
    # so the boot id is part of it too.
    session: str | None = None


def find_panel(sys_root: Path = Path("/sys")) -> PanelPort | None:
    links = Path(sys_root) / "bus/usb-serial/devices"
    try:
        ttys = sorted(links.iterdir())
    except OSError:
        return None
    for link in ttys:
        try:
            usb_device = link.resolve().parent.parent
            vendor = (usb_device / "idVendor").read_text().strip()
            product = (usb_device / "idProduct").read_text().strip()
        except OSError:
            continue
        if (vendor, product) == (_VENDOR, _PRODUCT):
            bus_port = usb_device.name
            return PanelPort(f"/dev/{link.name}", bus_port, bus_port in STRONG_SUPPLY_PORTS, _session(usb_device))
    return None


def _session(usb_device: Path) -> str | None:
    try:
        bus = (usb_device / "busnum").read_text().strip()
        number = (usb_device / "devnum").read_text().strip()
    except OSError:
        return None
    try:
        boot = _BOOT_ID.read_text().strip()
    except OSError:
        boot = "?"
    return f"{usb_device.name}:{bus}:{number}:{boot}"


def port_holders(dev: str, proc_root: Path = Path("/proc"), own_pid: int | None = None) -> list[tuple[int, str]]:
    own = os.getpid() if own_pid is None else own_pid
    holders = []
    try:
        entries = list(Path(proc_root).iterdir())
    except OSError:
        return holders
    for entry in entries:
        if not entry.name.isdigit() or int(entry.name) == own:
            continue
        try:
            fds = list((entry / "fd").iterdir())
        except OSError:
            continue
        if any(_points_to(fd, dev) for fd in fds):
            try:
                comm = (entry / "comm").read_text().strip()
            except OSError:
                comm = ""
            holders.append((int(entry.name), comm))
    return sorted(holders)


def _points_to(fd: Path, dev: str) -> bool:
    try:
        return os.readlink(fd) == dev
    except OSError:
        return False
