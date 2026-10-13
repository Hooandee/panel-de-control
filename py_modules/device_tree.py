import functools
import os
import platform
from dataclasses import dataclass

# Decky runs under x86 emulation (FEX) on ARM handhelds, so platform.machine() and
# /proc/cpuinfo report an x86 CPU there. These kernel interfaces are not emulated.
_MIDR = "sys/devices/system/cpu/cpu0/regs/identification/midr_el1"
_DT = "proc/device-tree"
_SOC = "sys/devices/soc0"

_SOC_NAMES = {
    "qcom,sm8550": "Snapdragon 8 Gen 2",
    "qcom,qcs8550": "Snapdragon 8 Gen 2",
    "qcom,sm8650": "Snapdragon 8 Gen 3",
    "qcom,sm8750": "Snapdragon 8 Elite",
    "qcom,sm8250": "Snapdragon 865",
    "qcom,sm8450": "Snapdragon 8 Gen 1",
    "qcom,sm8475": "Snapdragon 8+ Gen 1",
    "qcom,qcs6490": "Snapdragon 6490",
    "qcom,sm6115": "Snapdragon 662",
}

_VENDORS = {
    "qcom": "qualcomm",
    "rockchip": "rockchip",
    "mediatek": "mediatek",
    "allwinner": "allwinner",
    "amlogic": "amlogic",
    "nvidia": "nvidia",
    "brcm": "broadcom",
}


@dataclass(frozen=True)
class DeviceTree:
    model: str
    compatible: tuple[str, ...]


def _read_bytes(path: str) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return b""


def _read_text(path: str) -> str:
    return _read_bytes(path).decode("utf-8", "replace").strip("\0").strip()


def is_arm(root: str = "/") -> bool:
    if os.path.exists(os.path.join(root, _MIDR)):
        return True
    has_dmi = bool(_read_text(os.path.join(root, "sys/class/dmi/id/sys_vendor")))
    return not has_dmi and bool(read_device_tree(root).compatible)


def read_device_tree(root: str = "/") -> DeviceTree:
    raw = _read_bytes(os.path.join(root, _DT, "compatible"))
    compatible = tuple(
        item for item in raw.decode("utf-8", "replace").split("\0") if item
    )
    return DeviceTree(model=_read_text(os.path.join(root, _DT, "model")), compatible=compatible)


def soc_vendor(tree: DeviceTree) -> str | None:
    for entry in reversed(tree.compatible):
        prefix = entry.split(",", 1)[0]
        if prefix in _VENDORS:
            return _VENDORS[prefix]
    return None


def soc_name(tree: DeviceTree, root: str = "/") -> str | None:
    for entry in tree.compatible:
        if entry in _SOC_NAMES:
            return _SOC_NAMES[entry]
    family = _read_text(os.path.join(root, _SOC, "family"))
    machine = _read_text(os.path.join(root, _SOC, "machine"))
    name = " ".join(part for part in (family, machine) if part)
    return name or None


_HOST_ROOT = "/proc/self/root"


@functools.lru_cache(maxsize=1)
def runs_emulated() -> bool:
    """x86 Python on an ARM kernel: the plugin runs under FEX."""
    return is_arm() and platform.machine() in ("x86_64", "i686", "i386")


def host_binary(path: str, host_root: str = _HOST_ROOT) -> str:
    # FEX runs any program launched from the emulated plugin from its x86 rootfs copy, which
    # costs about a second per spawn; the host's own binary through /proc/self/root runs
    # natively. Programs only the emulator ships keep their path.
    if not runs_emulated() or not os.path.isabs(path):
        return path
    native = os.path.join(host_root, path.lstrip("/"))
    return native if os.access(native, os.X_OK) else path
