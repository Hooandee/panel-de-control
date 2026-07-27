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


def legion_go_s_83n6_rail_floors(device, root: str = "/") -> dict[str, int]:
    if (
        getattr(device, "key", None) == "legion_go_s"
        and _read_dmi(root, "sys_vendor").casefold() == "lenovo"
        and _read_dmi(root, "product_name").casefold() == "83n6"
    ):
        return {"pl2": 15, "pl3": 20}
    return {}
