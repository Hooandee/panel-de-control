import os


def _read_dmi(root: str, field: str) -> str:
    try:
        with open(os.path.join(root, "sys/class/dmi/id", field)) as handle:
            return handle.read().strip()
    except OSError:
        return ""


def is_gpd_win_mini_2025(device, root: str = "/") -> bool:
    return (
        getattr(device, "key", None) == "gpd_win_mini_2025"
        and _read_dmi(root, "sys_vendor").casefold() == "gpd"
        and _read_dmi(root, "product_name").casefold() == "g1617-02"
    )


def is_legion_go_s_83n6(device, root: str = "/") -> bool:
    return (
        getattr(device, "key", None) == "legion_go_s"
        and _read_dmi(root, "sys_vendor").casefold() == "lenovo"
        and _read_dmi(root, "product_name").casefold() == "83n6"
    )


def legion_go_s_83l3_firmware_attr_quirks(device, root: str = "/") -> dict:
    if (
        getattr(device, "key", None) != "legion_go_s"
        or _read_dmi(root, "sys_vendor").casefold() != "lenovo"
        or _read_dmi(root, "product_name").casefold() != "83l3"
    ):
        return {}
    return {"readback_settle_delays": (0.05, 0.10, 0.20, 0.40)}


def legion_go_s_83n6_rail_floors(device, root: str = "/") -> dict[str, int]:
    if is_legion_go_s_83n6(device, root):
        return {"pl2": 15, "pl3": 20}
    return {}


def legion_go_s_83n6_firmware_attr_quirks(device, root: str = "/") -> dict:
    if not is_legion_go_s_83n6(device, root):
        return {}
    return {
        "ignored_live_maxes": {"pl1": 15, "pl2": 15, "pl3": 20},
        "cap_boost_to_active": True,
    }
